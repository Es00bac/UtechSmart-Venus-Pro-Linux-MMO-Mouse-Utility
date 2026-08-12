// Decompile every function whose entry point falls in one or more address ranges.
// Arguments: output.txt start1 end1 [start2 end2 ...]

import java.io.File;
import java.io.PrintWriter;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;

public class GhidraDecompileRange extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 3 || args.length % 2 == 0) {
            throw new IllegalArgumentException("expected output plus start/end address pairs");
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try (PrintWriter out = new PrintWriter(new File(args[0]))) {
            FunctionIterator iterator = currentProgram.getFunctionManager().getFunctions(true);
            while (iterator.hasNext()) {
                Function function = iterator.next();
                Address entry = function.getEntryPoint();
                boolean selected = false;
                for (int i = 1; i < args.length; i += 2) {
                    Address start = currentProgram.getAddressFactory().getAddress(args[i]);
                    Address end = currentProgram.getAddressFactory().getAddress(args[i + 1]);
                    if (entry.compareTo(start) >= 0 && entry.compareTo(end) <= 0) {
                        selected = true;
                        break;
                    }
                }
                if (!selected || monitor.isCancelled()) {
                    continue;
                }

                out.printf("===== %s @ %s =====%n%n", function.getName(), entry);
                DecompileResults result = decompiler.decompileFunction(function, 90, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    out.println(result.getDecompiledFunction().getC());
                } else {
                    out.println("DECOMPILE FAILED: " + result.getErrorMessage());
                }
                out.println();
            }
        } finally {
            decompiler.dispose();
        }
    }
}
