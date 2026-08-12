// Export decompiled functions that reference protocol-related strings.
// Run with analyzeHeadless ... -postScript GhidraProtocolExport.java output.txt

import java.io.File;
import java.io.PrintWriter;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class GhidraProtocolExport extends GhidraScript {
    private static final String[] NEEDLES = {
        "macrohasmskey", "stmacro_to_hdmacro", "hdmacro_to_stmacro",
        "writeeeprom", "readeeprom", "waitnotify", "cread:",
        "bcddevice", "start apply", "markled", "hgetprofile",
        "getprofile", "getmacroname", "setfeature", "challenge"
    };

    private boolean interesting(String value) {
        String lower = value.toLowerCase(Locale.ROOT);
        for (String needle : NEEDLES) {
            if (lower.contains(needle)) {
                return true;
            }
        }
        return false;
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("expected one output-file argument");
        }

        Set<Function> functions = new LinkedHashSet<>();
        try (PrintWriter out = new PrintWriter(new File(args[0]))) {
            out.println("PROGRAM " + currentProgram.getName());
            out.println();

            for (Data data : currentProgram.getListing().getDefinedData(true)) {
                Object value = data.getValue();
                if (!(value instanceof String) || !interesting((String) value)) {
                    continue;
                }
                out.printf("STRING %s %s%n", data.getAddress(), value);
                ReferenceIterator refs = currentProgram.getReferenceManager()
                    .getReferencesTo(data.getAddress());
                while (refs.hasNext()) {
                    Reference ref = refs.next();
                    Function function = currentProgram.getFunctionManager()
                        .getFunctionContaining(ref.getFromAddress());
                    out.printf("  XREF %s%s%n", ref.getFromAddress(),
                        function == null ? "" : " in " + function.getName() + "@" + function.getEntryPoint());
                    if (function != null) {
                        functions.add(function);
                    }
                }
            }

            DecompInterface decompiler = new DecompInterface();
            decompiler.openProgram(currentProgram);
            for (Function function : functions) {
                if (monitor.isCancelled()) {
                    break;
                }
                out.println();
                out.printf("===== %s @ %s =====%n", function.getName(), function.getEntryPoint());
                DecompileResults result = decompiler.decompileFunction(function, 90, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    out.println(result.getDecompiledFunction().getC());
                } else {
                    out.println("DECOMPILE FAILED: " + result.getErrorMessage());
                }
            }
            decompiler.dispose();
        }
    }
}
