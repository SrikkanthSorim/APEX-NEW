package com.javaapex.testinventory;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.openrewrite.ExecutionContext;
import org.openrewrite.InMemoryExecutionContext;
import org.openrewrite.SourceFile;
import org.openrewrite.java.JavaIsoVisitor;
import org.openrewrite.java.JavaParser;
import org.openrewrite.java.tree.Expression;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.JavaType;
import org.openrewrite.java.tree.NameTree;
import org.openrewrite.java.tree.Statement;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * Scans a single-module Maven/Gradle project's {@code src/main/java} and
 * {@code src/test/java} trees using the OpenRewrite Java parser/LST (not
 * regex or filename-only heuristics) and produces structured JSON metadata:
 * production classes (with dependencies, methods, branch counts, thrown
 * exceptions, existing-test linkage) and test classes (with real test
 * methods detected via JUnit/TestNG annotation presence on the parsed AST,
 * not just files ending in "Test.java").
 *
 * <p>The parser is built without a resolved project dependency classpath
 * (downloading the full Maven/Gradle dependency graph just to type-attribute
 * library annotations would be slow and is unnecessary here) -- annotation
 * identification instead cross-references each compilation unit's own
 * {@code import} declarations, which are read from the same parsed LST.
 */
final class InventoryScanner {

    private static final Set<String> TEST_METHOD_ANNOTATIONS = new HashSet<>(Arrays.asList(
            "Test", "ParameterizedTest", "RepeatedTest", "TestFactory", "TestTemplate"
    ));
    private static final Set<String> DISABLED_ANNOTATIONS = new HashSet<>(Arrays.asList("Disabled", "Ignore"));
    private static final Set<String> PRIMITIVE_OR_TRIVIAL_TYPES = new HashSet<>(Arrays.asList(
            "int", "long", "double", "float", "boolean", "char", "byte", "short", "void",
            "Integer", "Long", "Double", "Float", "Boolean", "Character", "Byte", "Short",
            "String", "Object", "Logger", "Class"
    ));

    private final ObjectMapper mapper = new ObjectMapper();

    String scanToJson(Path projectDir) throws IOException {
        Map<String, Object> result = scan(projectDir);
        return mapper.writerWithDefaultPrettyPrinter().writeValueAsString(result);
    }

    Map<String, Object> scan(Path projectDir) throws IOException {
        Path mainRoot = projectDir.resolve("src/main/java");
        Path testRoot = projectDir.resolve("src/test/java");

        List<Path> mainFiles = findJavaFiles(mainRoot);
        List<Path> testFiles = findJavaFiles(testRoot);

        List<String> parseErrors = new ArrayList<>();
        JavaParser parser = JavaParser.fromJavaVersion().logCompilationWarningsAndErrors(false).build();
        ExecutionContext ctx = new InMemoryExecutionContext(t -> parseErrors.add(t.toString()));

        List<J.CompilationUnit> mainUnits = parse(parser, mainFiles, projectDir, ctx);
        List<J.CompilationUnit> testUnits = parse(parser, testFiles, projectDir, ctx);

        List<Map<String, Object>> productionClasses = new ArrayList<>();
        for (J.CompilationUnit cu : mainUnits) {
            productionClasses.addAll(describeClasses(cu, projectDir, false));
        }

        List<Map<String, Object>> testClasses = new ArrayList<>();
        for (J.CompilationUnit cu : testUnits) {
            testClasses.addAll(describeClasses(cu, projectDir, true));
        }

        linkExistingTests(productionClasses, testClasses);

        Map<String, Object> envelope = new LinkedHashMap<>();
        envelope.put("projectDir", projectDir.toString());
        envelope.put("productionFileCount", mainFiles.size());
        envelope.put("testFileCount", testFiles.size());
        envelope.put("productionClasses", productionClasses);
        envelope.put("testClasses", testClasses);
        envelope.put("parseErrors", parseErrors);
        return envelope;
    }

    // -- parsing -------------------------------------------------------- //

    private static List<Path> findJavaFiles(Path root) throws IOException {
        if (!Files.isDirectory(root)) {
            return new ArrayList<>();
        }
        try (Stream<Path> walk = Files.walk(root)) {
            return walk.filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".java"))
                    .filter(p -> !p.getFileName().toString().equals("package-info.java"))
                    .filter(p -> !p.getFileName().toString().equals("module-info.java"))
                    .collect(Collectors.toList());
        }
    }

    private static List<J.CompilationUnit> parse(JavaParser parser, List<Path> files, Path relativeTo, ExecutionContext ctx) {
        if (files.isEmpty()) {
            return new ArrayList<>();
        }
        return parser.parse(files, relativeTo, ctx)
                .filter(J.CompilationUnit.class::isInstance)
                .map(J.CompilationUnit.class::cast)
                .collect(Collectors.toList());
    }

    // -- per-compilation-unit description -------------------------------- //

    private List<Map<String, Object>> describeClasses(J.CompilationUnit cu, Path projectDir, boolean isTestRoot) {
        String packageName = cu.getPackageDeclaration() == null
                ? ""
                : AstText.dottedName(cu.getPackageDeclaration().getExpression());
        Map<String, String> importMap = buildImportMap(cu);
        String relativePath = relativize(projectDir, cu.getSourcePath());

        List<Map<String, Object>> classes = new ArrayList<>();
        for (J.ClassDeclaration classDecl : cu.getClasses()) {
            classes.add(isTestRoot
                    ? describeTestClass(classDecl, packageName, relativePath, importMap)
                    : describeProductionClass(classDecl, packageName, relativePath, importMap));
        }
        return classes;
    }

    private Map<String, String> buildImportMap(J.CompilationUnit cu) {
        Map<String, String> importMap = new HashMap<>();
        for (J.Import imp : cu.getImports()) {
            String qualified = AstText.qualifiedNameFromImport(imp.getQualid());
            if (qualified.endsWith(".*")) {
                continue;
            }
            String simple = AstText.lastSegment(qualified);
            importMap.put(simple, qualified);
        }
        return importMap;
    }

    private static String relativize(Path projectDir, Path sourcePath) {
        try {
            Path abs = sourcePath.isAbsolute() ? sourcePath : projectDir.resolve(sourcePath);
            return projectDir.toAbsolutePath().normalize()
                    .relativize(abs.toAbsolutePath().normalize())
                    .toString().replace('\\', '/');
        } catch (IllegalArgumentException e) {
            return sourcePath.toString().replace('\\', '/');
        }
    }

    // -- production classes ---------------------------------------------- //

    private Map<String, Object> describeProductionClass(
            J.ClassDeclaration classDecl, String packageName, String relativePath, Map<String, String> importMap
    ) {
        boolean isInterface = classDecl.getKind() == J.ClassDeclaration.Kind.Type.Interface;
        boolean isAbstract = classDecl.getModifiers().stream().anyMatch(m -> m.getType() == J.Modifier.Type.Abstract);
        List<String> annotations = classDecl.getLeadingAnnotations().stream()
                .map(InventoryScanner::annotationSimpleName)
                .collect(Collectors.toList());

        List<Map<String, Object>> methods = new ArrayList<>();
        boolean hasMainMethod = false;
        for (Statement statement : classDecl.getBody().getStatements()) {
            if (!(statement instanceof J.MethodDeclaration)) {
                continue;
            }
            J.MethodDeclaration method = (J.MethodDeclaration) statement;
            if (method.isConstructor()) {
                continue;
            }
            if (isMainMethod(method)) {
                hasMainMethod = true;
            }
            methods.add(describeMethod(method));
        }

        List<String> dependencies = extractDependencies(classDecl);
        String classType = classifyClassType(classDecl, annotations, methods, isInterface, isAbstract, hasMainMethod);

        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("className", classDecl.getSimpleName());
        entry.put("packageName", packageName);
        entry.put("sourcePath", relativePath);
        entry.put("classType", classType);
        entry.put("isInterface", isInterface);
        entry.put("isAbstract", isAbstract);
        entry.put("annotations", annotations);
        entry.put("dependencies", dependencies);
        entry.put("methods", methods);
        entry.put("existingTestClass", null);
        entry.put("existingTestCount", 0);
        return entry;
    }

    private Map<String, Object> describeMethod(J.MethodDeclaration method) {
        List<Map<String, Object>> parameters = new ArrayList<>();
        for (Statement param : method.getParameters()) {
            if (param instanceof J.VariableDeclarations) {
                J.VariableDeclarations vd = (J.VariableDeclarations) param;
                String type = AstText.simpleTypeName(vd.getTypeExpression());
                for (J.VariableDeclarations.NamedVariable variable : vd.getVariables()) {
                    Map<String, Object> p = new LinkedHashMap<>();
                    p.put("name", variable.getSimpleName());
                    p.put("type", type);
                    parameters.add(p);
                }
            }
        }

        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("name", method.getSimpleName());
        entry.put("visibility", visibilityOf(method.getModifiers()));
        entry.put("returnType", AstText.simpleTypeName(method.getReturnTypeExpression()));
        entry.put("parameters", parameters);
        entry.put("branchCount", countBranches(method));
        boolean declaresCheckedExceptions = method.getThrows() != null && !method.getThrows().isEmpty();
        entry.put("throwsExceptions", declaresCheckedExceptions || hasTryCatch(method) || hasThrowStatement(method));
        return entry;
    }

    private static boolean isMainMethod(J.MethodDeclaration method) {
        return "main".equals(method.getSimpleName())
                && method.getModifiers().stream().anyMatch(m -> m.getType() == J.Modifier.Type.Static)
                && method.getParameters().size() == 1;
    }

    private List<String> extractDependencies(J.ClassDeclaration classDecl) {
        Set<String> dependencies = new LinkedHashSet<>();

        for (Statement statement : classDecl.getBody().getStatements()) {
            if (statement instanceof J.VariableDeclarations) {
                J.VariableDeclarations vd = (J.VariableDeclarations) statement;
                boolean isStatic = vd.getModifiers().stream().anyMatch(m -> m.getType() == J.Modifier.Type.Static);
                if (isStatic) {
                    continue;
                }
                String type = AstText.simpleTypeName(vd.getTypeExpression());
                if (isMeaningfulDependencyType(type)) {
                    dependencies.add(type);
                }
            }
        }

        for (Statement statement : classDecl.getBody().getStatements()) {
            if (statement instanceof J.MethodDeclaration && ((J.MethodDeclaration) statement).isConstructor()) {
                J.MethodDeclaration ctor = (J.MethodDeclaration) statement;
                for (Statement param : ctor.getParameters()) {
                    if (param instanceof J.VariableDeclarations) {
                        String type = AstText.simpleTypeName(((J.VariableDeclarations) param).getTypeExpression());
                        if (isMeaningfulDependencyType(type)) {
                            dependencies.add(type);
                        }
                    }
                }
            }
        }
        return new ArrayList<>(dependencies);
    }

    private static boolean isMeaningfulDependencyType(String type) {
        if (type == null || type.isEmpty()) {
            return false;
        }
        String base = type.contains("<") ? type.substring(0, type.indexOf('<')) : type;
        return !PRIMITIVE_OR_TRIVIAL_TYPES.contains(base);
    }

    // -- classType heuristic ---------------------------------------------- //

    private static String classifyClassType(
            J.ClassDeclaration classDecl, List<String> annotations, List<Map<String, Object>> methods,
            boolean isInterface, boolean isAbstract, boolean hasMainMethod
    ) {
        Set<String> annSet = new HashSet<>(annotations);
        String name = classDecl.getSimpleName();
        boolean hasNonTrivialMethod = methods.stream().anyMatch(InventoryScanner::isNonTrivialMethod);
        boolean allTrivial = !methods.isEmpty() && methods.stream().allMatch(InventoryScanner::isTrivialAccessor);

        if (hasMainMethod && annSet.contains("SpringBootApplication")) {
            return "MAIN_APPLICATION";
        }
        if (annSet.contains("Configuration") || annSet.contains("SpringBootApplication")) {
            return "CONFIGURATION";
        }
        if (annSet.contains("RestController") || annSet.contains("Controller")) {
            return "CONTROLLER";
        }
        if (annSet.contains("Entity")) {
            return "ENTITY";
        }
        // Interface/abstract-class detection must run BEFORE the name-based
        // Service/Validator/Converter/Utility heuristics below -- an
        // interface named e.g. "ITodoService" or "TodoService" (with a
        // separate "TodoServiceImpl" concrete class) must never be
        // classified SERVICE and offered up for test generation: it has no
        // method bodies to test. Only its concrete implementation should be.
        if (isInterface) {
            if (name.endsWith("Repository") || annSet.contains("Repository")) {
                return "REPOSITORY_INTERFACE";
            }
            return "INTERFACE_ONLY";
        }
        if (isAbstract) {
            return "ABSTRACT_CLASS";
        }
        if (name.endsWith("Exception")) {
            return "EXCEPTION";
        }
        if (annSet.contains("Service") || name.endsWith("Service") || name.endsWith("ServiceImpl")) {
            return "SERVICE";
        }
        if (name.endsWith("Validator")) {
            return "VALIDATOR";
        }
        if (name.endsWith("Converter") || name.endsWith("Mapper")) {
            return "CONVERTER";
        }
        if (name.endsWith("Util") || name.endsWith("Utils") || name.endsWith("Helper")) {
            return hasNonTrivialMethod ? "UTILITY" : "CONSTANTS";
        }
        if (name.endsWith("Dto") || name.endsWith("DTO") || name.endsWith("Request") || name.endsWith("Response")
                || (allTrivial && !methods.isEmpty())) {
            return "DTO";
        }
        if (methods.isEmpty()) {
            return "CONSTANTS";
        }
        return hasNonTrivialMethod ? "DOMAIN" : "OTHER";
    }

    @SuppressWarnings("unchecked")
    private static boolean isNonTrivialMethod(Map<String, Object> method) {
        Object branchCount = method.get("branchCount");
        return branchCount instanceof Integer && (Integer) branchCount > 0;
    }

    @SuppressWarnings("unchecked")
    private static boolean isTrivialAccessor(Map<String, Object> method) {
        String name = String.valueOf(method.get("name"));
        Object branchCount = method.get("branchCount");
        int branches = branchCount instanceof Integer ? (Integer) branchCount : 0;
        List<?> parameters = (List<?>) method.get("parameters");
        boolean isGetter = (name.startsWith("get") || name.startsWith("is")) && parameters.isEmpty();
        boolean isSetter = name.startsWith("set") && parameters.size() == 1;
        return branches == 0 && (isGetter || isSetter);
    }

    // -- test classes ------------------------------------------------------ //

    private Map<String, Object> describeTestClass(
            J.ClassDeclaration classDecl, String packageName, String relativePath, Map<String, String> importMap
    ) {
        boolean mockitoUsed = importMap.values().stream().anyMatch(v -> v.startsWith("org.mockito"));
        List<String> classAnnotations = classDecl.getLeadingAnnotations().stream()
                .map(InventoryScanner::annotationSimpleName)
                .collect(Collectors.toList());
        if (!mockitoUsed) {
            mockitoUsed = classAnnotations.stream().anyMatch(a -> a.equals("ExtendWith") || a.equals("Mock"));
        }

        List<Map<String, Object>> testMethods = new ArrayList<>();
        Set<String> frameworksSeen = new LinkedHashSet<>();
        for (Statement statement : classDecl.getBody().getStatements()) {
            if (!(statement instanceof J.MethodDeclaration)) {
                continue;
            }
            J.MethodDeclaration method = (J.MethodDeclaration) statement;
            List<String> methodAnnotations = method.getLeadingAnnotations().stream()
                    .map(InventoryScanner::annotationSimpleName)
                    .collect(Collectors.toList());
            boolean isTestMethod = methodAnnotations.stream().anyMatch(TEST_METHOD_ANNOTATIONS::contains);
            if (!isTestMethod) {
                continue;
            }
            boolean disabled = methodAnnotations.stream().anyMatch(DISABLED_ANNOTATIONS::contains);
            String framework = detectFramework(method, importMap);
            frameworksSeen.add(framework);

            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("name", method.getSimpleName());
            entry.put("annotations", methodAnnotations);
            entry.put("disabled", disabled);
            entry.put("framework", framework);
            testMethods.add(entry);
        }

        String testFramework = frameworksSeen.contains("TESTNG") ? "TESTNG"
                : frameworksSeen.contains("JUNIT_4") ? "JUNIT_4"
                : frameworksSeen.contains("JUNIT_5") ? "JUNIT_5"
                : "UNKNOWN";

        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("className", classDecl.getSimpleName());
        entry.put("packageName", packageName);
        entry.put("sourcePath", relativePath);
        entry.put("testFramework", testFramework);
        entry.put("testMethods", testMethods);
        entry.put("mockitoUsed", mockitoUsed);
        entry.put("testedClassNameGuess", guessTestedClassName(classDecl.getSimpleName()));
        return entry;
    }

    private static String guessTestedClassName(String testClassName) {
        if (testClassName.endsWith("Test")) {
            return testClassName.substring(0, testClassName.length() - "Test".length());
        }
        if (testClassName.endsWith("Tests")) {
            return testClassName.substring(0, testClassName.length() - "Tests".length());
        }
        if (testClassName.startsWith("Test")) {
            return testClassName.substring("Test".length());
        }
        return testClassName;
    }

    private static String detectFramework(J.MethodDeclaration method, Map<String, String> importMap) {
        for (J.Annotation annotation : method.getLeadingAnnotations()) {
            String simple = annotationSimpleName(annotation);
            String qualified = importMap.get(simple);
            if (qualified == null) {
                continue;
            }
            if (qualified.startsWith("org.junit.jupiter")) {
                return "JUNIT_5";
            }
            if (qualified.equals("org.junit.Test")) {
                return "JUNIT_4";
            }
            if (qualified.startsWith("org.testng")) {
                return "TESTNG";
            }
        }
        // Bare @Test with no resolvable import (e.g. wildcard import) -- JUnit 5
        // is the default assumption for this phase.
        return "JUNIT_5";
    }

    // -- cross-linking existing tests to production classes ---------------- //

    private void linkExistingTests(List<Map<String, Object>> productionClasses, List<Map<String, Object>> testClasses) {
        for (Map<String, Object> production : productionClasses) {
            String className = String.valueOf(production.get("className"));
            String packageName = String.valueOf(production.get("packageName"));

            for (Map<String, Object> test : testClasses) {
                String guess = String.valueOf(test.get("testedClassNameGuess"));
                String testPackage = String.valueOf(test.get("packageName"));
                if (guess.equals(className) && testPackage.equals(packageName)) {
                    production.put("existingTestClass", test.get("className"));
                    @SuppressWarnings("unchecked")
                    List<Object> testMethods = (List<Object>) test.get("testMethods");
                    production.put("existingTestCount", testMethods.size());
                    break;
                }
            }
        }
    }

    // -- shared AST helpers ------------------------------------------------ //

    private static String annotationSimpleName(J.Annotation annotation) {
        NameTree nameTree = annotation.getAnnotationType();
        String dotted = nameTree instanceof Expression ? AstText.dottedName((Expression) nameTree) : nameTree.toString();
        return AstText.lastSegment(dotted);
    }

    private static String visibilityOf(List<J.Modifier> modifiers) {
        for (J.Modifier modifier : modifiers) {
            if (modifier.getType() == J.Modifier.Type.Public) {
                return "public";
            }
            if (modifier.getType() == J.Modifier.Type.Protected) {
                return "protected";
            }
            if (modifier.getType() == J.Modifier.Type.Private) {
                return "private";
            }
        }
        return "package-private";
    }

    private static int countBranches(J.MethodDeclaration method) {
        if (method.getBody() == null) {
            return 0;
        }
        AtomicInteger counter = new AtomicInteger();
        JavaIsoVisitor<AtomicInteger> visitor = new JavaIsoVisitor<AtomicInteger>() {
            @Override
            public J.If visitIf(J.If iff, AtomicInteger count) {
                count.incrementAndGet();
                return super.visitIf(iff, count);
            }

            @Override
            public J.Switch visitSwitch(J.Switch switchStatement, AtomicInteger count) {
                count.incrementAndGet();
                return super.visitSwitch(switchStatement, count);
            }
        };
        visitor.visit(method.getBody(), counter);
        return counter.get();
    }

    private static boolean hasTryCatch(J.MethodDeclaration method) {
        if (method.getBody() == null) {
            return false;
        }
        AtomicBoolean found = new AtomicBoolean(false);
        JavaIsoVisitor<AtomicBoolean> visitor = new JavaIsoVisitor<AtomicBoolean>() {
            @Override
            public J.Try visitTry(J.Try tryable, AtomicBoolean flag) {
                flag.set(true);
                return super.visitTry(tryable, flag);
            }
        };
        visitor.visit(method.getBody(), found);
        return found.get();
    }

    private static boolean hasThrowStatement(J.MethodDeclaration method) {
        if (method.getBody() == null) {
            return false;
        }
        AtomicBoolean found = new AtomicBoolean(false);
        JavaIsoVisitor<AtomicBoolean> visitor = new JavaIsoVisitor<AtomicBoolean>() {
            @Override
            public J.Throw visitThrow(J.Throw thrown, AtomicBoolean flag) {
                flag.set(true);
                return super.visitThrow(thrown, flag);
            }
        };
        visitor.visit(method.getBody(), found);
        return found.get();
    }
}
