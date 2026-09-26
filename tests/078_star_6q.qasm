OPENQASM 3.0;
include "stdgates.inc";

qubit[6] q;

cx q[3], q[0];
cx q[4], q[0];
cx q[5], q[0];
cx q[2], q[0];
cx q[1], q[0];
cx q[0], q[3];
cx q[0], q[4];
