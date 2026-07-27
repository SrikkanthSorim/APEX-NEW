package com.javaapex.testinventory;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

/**
 * CLI entry point. Invoked from the Python backend via `java -jar rewrite-test-inventory.jar
 * &lt;mode&gt; ...` (see app/infrastructure/testing/rewrite_inventory_tool.py and
 * rewrite_test_validator.py). Two modes:
 *
 * <pre>
 *   inventory &lt;projectDir&gt; &lt;outputJsonPath&gt;
 *   validate &lt;sourceFilePath&gt; &lt;outputJsonPath&gt;
 * </pre>
 *
 * Output JSON is written to outputJsonPath and also echoed to stdout so the
 * caller can read it from either the file or the captured process output.
 */
public final class Main {

    private Main() {
    }

    public static void main(String[] args) {
        if (args.length < 3) {
            System.err.println("Usage: rewrite-test-inventory <inventory|validate> <input> <outputJsonPath>");
            System.exit(2);
            return;
        }
        String mode = args[0];
        try {
            String result;
            switch (mode) {
                case "inventory":
                    result = new InventoryScanner().scanToJson(Paths.get(args[1]));
                    break;
                case "validate": {
                    String source = Files.readString(Paths.get(args[1]), StandardCharsets.UTF_8);
                    result = new TestSourceValidator().validateToJson(source);
                    break;
                }
                default:
                    System.err.println("Unknown mode: " + mode);
                    System.exit(2);
                    return;
            }
            Files.writeString(Paths.get(args[2]), result, StandardCharsets.UTF_8);
            System.out.println(result);
        } catch (Exception e) {
            System.err.println("rewrite-test-inventory failed: " + e);
            e.printStackTrace();
            System.exit(1);
        }
    }

}
