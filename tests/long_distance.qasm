OPENQASM 3.0;
include "stdgates.inc";

qubit[4] q;

cx q[0], q[3];
cx q[1], q[2];
