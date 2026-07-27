package com.javaapex.testinventory;

import org.openrewrite.java.tree.Expression;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.NameTree;
import org.openrewrite.java.tree.TypeTree;

/**
 * Small helpers to turn LST name/type nodes into plain dotted-name strings
 * without needing full type attribution (the tool intentionally parses
 * without a resolved dependency classpath -- see InventoryScanner).
 */
final class AstText {

    private AstText() {
    }

    static String dottedName(Expression expression) {
        if (expression == null) {
            return "";
        }
        if (expression instanceof J.Identifier) {
            return ((J.Identifier) expression).getSimpleName();
        }
        if (expression instanceof J.FieldAccess) {
            J.FieldAccess fieldAccess = (J.FieldAccess) expression;
            String target = dottedName(fieldAccess.getTarget());
            String name = fieldAccess.getName().getSimpleName();
            return target.isEmpty() ? name : target + "." + name;
        }
        if (expression instanceof J.ParameterizedType) {
            NameTree clazz = ((J.ParameterizedType) expression).getClazz();
            return clazz instanceof Expression ? dottedName((Expression) clazz) : clazz.toString();
        }
        return expression.toString();
    }

    static String simpleTypeName(TypeTree typeTree) {
        if (typeTree == null) {
            return "void";
        }
        if (typeTree instanceof J.Identifier) {
            return ((J.Identifier) typeTree).getSimpleName();
        }
        if (typeTree instanceof J.ParameterizedType) {
            J.ParameterizedType parameterized = (J.ParameterizedType) typeTree;
            NameTree clazz = parameterized.getClazz();
            String base = clazz instanceof TypeTree ? simpleTypeName((TypeTree) clazz) : clazz.toString();
            if (parameterized.getTypeParameters() == null || parameterized.getTypeParameters().isEmpty()) {
                return base;
            }
            StringBuilder sb = new StringBuilder(base).append("<");
            for (int i = 0; i < parameterized.getTypeParameters().size(); i++) {
                if (i > 0) {
                    sb.append(", ");
                }
                Object param = parameterized.getTypeParameters().get(i);
                if (param instanceof TypeTree) {
                    sb.append(simpleTypeName((TypeTree) param));
                } else {
                    sb.append(param);
                }
            }
            return sb.append(">").toString();
        }
        if (typeTree instanceof J.ArrayType) {
            return simpleTypeName(((J.ArrayType) typeTree).getElementType()) + "[]";
        }
        if (typeTree instanceof J.FieldAccess) {
            return lastSegment(dottedName((J.FieldAccess) typeTree));
        }
        if (typeTree instanceof J.Primitive) {
            return typeTree.toString();
        }
        return typeTree.toString().trim();
    }

    static String qualifiedNameFromImport(NameTree nameTree) {
        if (nameTree instanceof Expression) {
            return dottedName((Expression) nameTree);
        }
        return nameTree.toString();
    }

    static String lastSegment(String dotted) {
        if (dotted == null || dotted.isEmpty()) {
            return dotted;
        }
        int idx = dotted.lastIndexOf('.');
        return idx == -1 ? dotted : dotted.substring(idx + 1);
    }
}
