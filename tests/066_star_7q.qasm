OPENQASM 3.0;
include "stdgates.inc";

qubit[7] q;

cx q[6], q[4];
cx q[2], q[4];
cx q[1], q[4];
cx q[3], q[4];
cx q[0], q[4];
cx q[5], q[4];
cx q[4], q[6];
cx q[4], q[2];
