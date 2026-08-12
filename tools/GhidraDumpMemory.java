// Dump initialized memory as hex. Arguments: output.txt address length

import java.io.File;
import java.io.PrintWriter;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;

public class GhidraDumpMemory extends GhidraScript {
    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 3) {
            throw new IllegalArgumentException("expected output, address, and byte length");
        }
        Address address = currentProgram.getAddressFactory().getAddress(args[1]);
        int length = Integer.decode(args[2]);
        byte[] data = new byte[length];
        currentProgram.getMemory().getBytes(address, data);
        try (PrintWriter out = new PrintWriter(new File(args[0]))) {
            for (int offset = 0; offset < data.length; offset += 16) {
                out.printf("%s  ", address.add(offset));
                int end = Math.min(offset + 16, data.length);
                for (int i = offset; i < end; i++) {
                    out.printf("%02x", data[i] & 0xff);
                    if (i + 1 < end) {
                        out.print(" ");
                    }
                }
                out.println();
            }
        }
    }
}
