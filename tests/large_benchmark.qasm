OPENQASM 3.0;
include "stdgates.inc";

qubit[10] q;

cx q[0], q[9];
cx q[1], q[8];
cx q[2], q[7];
cx q[3], q[6];
cx q[4], q[5];
cx q[0], q[8];
cx q[1], q[9];
cx q[2], q[6];
cx q[3], q[7];
cx q[0], q[5];
cx q[1], q[6];
cx q[2], q[9];
