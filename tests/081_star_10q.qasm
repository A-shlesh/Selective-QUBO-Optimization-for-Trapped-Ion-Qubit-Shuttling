OPENQASM 3.0;
include "stdgates.inc";

qubit[10] q;

cx q[1], q[5];
cx q[8], q[5];
cx q[6], q[5];
cx q[4], q[5];
cx q[7], q[5];
cx q[2], q[5];
cx q[3], q[5];
cx q[0], q[5];
cx q[9], q[5];
cx q[5], q[1];
cx q[5], q[8];
cx q[5], q[6];
