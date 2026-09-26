OPENQASM 3.0;
include "stdgates.inc";

qubit[7] q;

cx q[5], q[2];
cx q[4], q[2];
cx q[6], q[2];
cx q[3], q[2];
cx q[1], q[2];
cx q[0], q[2];
cx q[2], q[5];
cx q[2], q[4];
