OPENQASM 3.0;
include "stdgates.inc";

qubit[19] q;

cx q[7], q[17];
cx q[0], q[17];
cx q[13], q[17];
cx q[10], q[17];
cx q[8], q[17];
cx q[11], q[17];
cx q[2], q[17];
cx q[1], q[17];
cx q[5], q[17];
cx q[14], q[17];
cx q[16], q[17];
cx q[18], q[17];
cx q[9], q[17];
cx q[6], q[17];
cx q[4], q[17];
cx q[15], q[17];
cx q[12], q[17];
cx q[3], q[17];
cx q[17], q[7];
cx q[17], q[0];
cx q[17], q[13];
cx q[17], q[10];
cx q[17], q[8];
cx q[17], q[11];
