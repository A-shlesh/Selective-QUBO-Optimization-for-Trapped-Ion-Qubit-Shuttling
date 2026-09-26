OPENQASM 3.0;
include "stdgates.inc";

qubit[8] q;

cx q[0], q[7];
cx q[1], q[6];
cx q[2], q[5];
cx q[3], q[4];
cx q[0], q[6];
cx q[1], q[7];
cx q[2], q[4];
cx q[3], q[5];
