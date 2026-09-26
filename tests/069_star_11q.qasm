OPENQASM 3.0;
include "stdgates.inc";

qubit[11] q;

cx q[5], q[3];
cx q[1], q[3];
cx q[9], q[3];
cx q[10], q[3];
cx q[2], q[3];
cx q[4], q[3];
cx q[7], q[3];
cx q[0], q[3];
cx q[8], q[3];
cx q[6], q[3];
cx q[3], q[5];
cx q[3], q[1];
cx q[3], q[9];
