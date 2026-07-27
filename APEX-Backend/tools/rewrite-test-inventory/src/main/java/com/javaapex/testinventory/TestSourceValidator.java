package com.javaapex.testinventory;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.openrewrite.ExecutionContext;
import org.openrewrite.InMemoryExecutionContext;
import org.openrewrite.SourceFile;
import org.openrewrite.java.JavaParser;
import org.openrewrite.java.tree.J;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Validates a single LLM-generated Java test source using the real
 * OpenRewrite Java parser before it is ever written into a repository (see
 * Step 6 of the unit-test generation pipeline: "Do not directly write the
 * raw LLM response into the repository"). Returns whether the source parses
 * cleanly, plus the package/class/imports actually found in it -- the Python
 * side cross-checks those against the intended target path and the
 * production-class inventory.
 */
final class TestSourceValidator {

    private final ObjectMapper mapper = new ObjectMapper();

    String validateToJson(String source) {
        Map<String, Object> result = validate(source);
        try {
            return mapper.writerWithDefaultPrettyPrinter().writeValueAsString(result);
        } catch (Exception e) {
            return "{\"valid\": false, \"parseErrors\": [\"" + e.getMessage() + "\"]}";
        }
    }

    Map<String, Object> validate(String source) {
        List<String> parseErrors = new ArrayList<>();
        JavaParser parser = JavaParser.fromJavaVersion().logCompilationWarningsAndErrors(false).build();
        ExecutionContext ctx = new InMemoryExecutionContext(t -> parseErrors.add(String.valueOf(t.getMessage())));

        Optional<SourceFile> parsed = parser.parse(ctx, source).findFirst();

        Map<String, Object> result = new LinkedHashMap<>();
        if (!parsed.isPresent() || !(parsed.get() instanceof J.CompilationUnit)) {
            result.put("valid", false);
            result.put("packageName", null);
            result.put("className", null);
            result.put("imports", new ArrayList<String>());
            result.put("parseErrors", parseErrors.isEmpty()
                    ? List.of("Source did not parse into a Java compilation unit.")
                    : parseErrors);
            return result;
        }

        J.CompilationUnit cu = (J.CompilationUnit) parsed.get();
        String packageName = cu.getPackageDeclaration() == null
                ? ""
                : AstText.dottedName(cu.getPackageDeclaration().getExpression());
        String className = cu.getClasses().isEmpty() ? null : cu.getClasses().get(0).getSimpleName();
        List<String> imports = new ArrayList<>();
        for (J.Import imp : cu.getImports()) {
            imports.add(AstText.qualifiedNameFromImport(imp.getQualid()));
        }

        result.put("valid", parseErrors.isEmpty() && className != null);
        result.put("packageName", packageName);
        result.put("className", className);
        result.put("imports", imports);
        result.put("parseErrors", parseErrors);
        return result;
    }
}
