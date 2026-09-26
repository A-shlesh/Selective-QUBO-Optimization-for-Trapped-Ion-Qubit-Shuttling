OPENQASM 3.0;
include "stdgates.inc";

qubit[5] q;

cx q[1], q[0];
cx q[4], q[2];
cx q[0], q[3];
cx q[2], q[4];
cx q[2], q[3];
cx q[4], q[0];
cx q[4], q[0];
cx q[2], q[3];
