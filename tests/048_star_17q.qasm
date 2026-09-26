OPENQASM 3.0;
include "stdgates.inc";

qubit[17] q;

cx q[11], q[6];
cx q[12], q[6];
cx q[16], q[6];
cx q[13], q[6];
cx q[1], q[6];
cx q[7], q[6];
cx q[14], q[6];
cx q[5], q[6];
cx q[8], q[6];
cx q[2], q[6];
cx q[4], q[6];
cx q[3], q[6];
cx q[9], q[6];
cx q[10], q[6];
cx q[0], q[6];
cx q[15], q[6];
cx q[6], q[11];
cx q[6], q[12];
cx q[6], q[16];
cx q[6], q[13];
cx q[6], q[1];
