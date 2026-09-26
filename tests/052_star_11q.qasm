OPENQASM 3.0;
include "stdgates.inc";

qubit[11] q;

cx q[6], q[7];
cx q[8], q[7];
cx q[9], q[7];
cx q[3], q[7];
cx q[4], q[7];
cx q[10], q[7];
cx q[2], q[7];
cx q[0], q[7];
cx q[1], q[7];
cx q[5], q[7];
cx q[7], q[6];
cx q[7], q[8];
cx q[7], q[9];
