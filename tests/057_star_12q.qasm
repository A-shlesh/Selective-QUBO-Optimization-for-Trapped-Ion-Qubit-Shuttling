OPENQASM 3.0;
include "stdgates.inc";

qubit[12] q;

cx q[4], q[9];
cx q[2], q[9];
cx q[8], q[9];
cx q[5], q[9];
cx q[10], q[9];
cx q[0], q[9];
cx q[7], q[9];
cx q[1], q[9];
cx q[3], q[9];
cx q[11], q[9];
cx q[6], q[9];
cx q[9], q[4];
cx q[9], q[2];
cx q[9], q[8];
cx q[9], q[5];
