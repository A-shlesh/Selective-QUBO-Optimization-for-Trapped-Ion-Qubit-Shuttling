OPENQASM 3.0;
include "stdgates.inc";

qubit[14] q;

cx q[10], q[12];
cx q[13], q[12];
cx q[0], q[12];
cx q[8], q[12];
cx q[5], q[12];
cx q[11], q[12];
cx q[7], q[12];
cx q[2], q[12];
cx q[4], q[12];
cx q[6], q[12];
cx q[9], q[12];
cx q[3], q[12];
cx q[1], q[12];
cx q[12], q[10];
cx q[12], q[13];
cx q[12], q[0];
cx q[12], q[8];
