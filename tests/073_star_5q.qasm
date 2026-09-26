OPENQASM 3.0;
include "stdgates.inc";

qubit[5] q;

cx q[3], q[1];
cx q[4], q[1];
cx q[0], q[1];
cx q[2], q[1];
cx q[1], q[3];
