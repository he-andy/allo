# Copyright Allo authors. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import numpy as np
import pytest
import allo
from allo.ir.types import int32, float32


def test_use_def_chain():
    def foo2(A: int32) -> int32:
        B: int32 = A + 1
        return B

    def foo(A: int32) -> int32:
        B: int32 = (A - 1) / (A + 1)
        C: int32 = foo2(A) + B
        return C

    def kernel(A: int32) -> int32:
        B: int32 = A + 1
        C: int32 = A * B
        D: int32 = (C + 1) - (B * A)
        E: int32 = foo(D)
        return E

    s = allo.customize(kernel)
    assert s.get_equivalent_variables("kernel:D") == set(
        ["foo2:0", "foo:0", "kernel:D"]
    )


def test_use_def_chain_array():
    def kernel(A: int32[32, 32], B: int32[32, 32]) -> int32[32, 32]:
        C: int32[32, 32] = 0
        for i, j in allo.grid(32, 32):
            for k in allo.reduction(32):
                C[i, j] += A[i, k] * B[k, j]
        return C

    def gemm(A: int32[32, 32], B: int32[32, 32]) -> int32[32, 32]:
        ret = kernel(A, B)
        return ret

    s = allo.customize(gemm, verbose=True)
    assert s.get_equivalent_variables("kernel:0") == set(["kernel:0", "gemm:0"])


def test_nested_functions():
    M, K, N = 32, 32, 32

    def matrix_add(A: int32[M, N]) -> int32[M, N]:
        B: int32[M, N] = 0
        for i, j in allo.grid(M, N):
            B[i, j] = A[i, j] + 1
        return B

    def gemm(A: int32[M, K], B: int32[K, N]) -> int32[M, N]:
        C: int32[M, N] = 0
        for i, j in allo.grid(M, N):
            for k in allo.reduction(K):
                C[i, j] += A[i, k] * B[k, j]
        return C

    def top(A: int32[M, K], B: int32[K, N]) -> int32[M, N]:
        C = gemm(A, B)
        D = matrix_add(C)
        return D

    # Separate compilation (just for testing)
    s_gemm = allo.customize(gemm)
    mod_gemm = s_gemm.build()

    # Top-level
    s = allo.customize(top)
    print(s.module)
    mod = s.build()

    # Testing
    np_A = np.random.randint(0, 10, size=(M, K)).astype(np.int32)
    np_B = np.random.randint(0, 10, size=(K, N)).astype(np.int32)
    np_D = np.matmul(np_A, np_B)
    np_C = mod_gemm(np_A, np_B)
    assert np.array_equal(np_C, np_D)

    np_A = np.random.randint(0, 10, size=(M, K)).astype(np.int32)
    np_B = np.random.randint(0, 10, size=(K, N)).astype(np.int32)
    np_D = np_A @ np_B + 1
    np_C = mod(np_A, np_B)
    assert np.array_equal(np_C, np_D)


def test_nested_functions_2():
    M, K, N = 32, 32, 32

    def gemm(A: int32[M, K], B: int32[K, N], C: int32[M, N]) -> None:
        for i, j in allo.grid(M, N):
            for k in allo.reduction(K):
                C[i, j] += A[i, k] * B[k, j]

    def top(A: int32[M, K], B: int32[K, N]) -> int32[M, N]:
        C: int32[M, N] = 0
        gemm(A, B, C)
        return C

    s1 = allo.customize(gemm)
    s1.reorder("k", "j")
    s1.partition(s1.C, dim=2)
    s1.buffer_at(s1.C, axis="i")
    s1.pipeline("j")
    # Top-level
    s = allo.customize(top)
    s.compose(s1)
    print(s.module)
    mod = s.build()

    # Testing
    np_A = np.random.randint(0, 100, size=(M, K)).astype(np.int32)
    np_B = np.random.randint(0, 100, size=(K, N)).astype(np.int32)
    np_C = mod(np_A, np_B)
    np_D = np.matmul(np_A, np_B)
    assert np.array_equal(np_C, np_D)
    print("Success!")


def test_compose_nested():
    M, N, K = 4, 4, 4

    def Linear_layer(
        inp: float32[M, K], W: float32[K, N], B: float32[N]
    ) -> float32[M, N]:
        outp: float32[M, N] = 0.0
        for i, j in allo.grid(M, N, name="gemm"):
            for k in allo.reduction(K):
                outp[i, j] += inp[i, k] * W[k, j]
        for i, j in allo.grid(M, N, name="bias"):
            outp[i, j] += B[j]
        return outp

    def Add1(inp: float32[M, N]) -> float32[M, N]:
        outp: float32[M, N] = 0.0
        for i, j in allo.grid(M, N, name="add"):
            outp[i, j] = inp[i, j] + 1.0
        return outp

    def Add2(inp: float32[M, N]) -> float32[M, N]:
        outp = Add1(inp)
        return outp

    def Top(inp: float32[M, K], W: float32[K, N], B: float32[N]) -> float32[M, N]:
        out0 = Linear_layer(inp, W, B)
        out1 = Add2(out0)
        return out1

    s_add2 = allo.customize(Add2)
    s_add2.partition(s_add2.inp)
    print(s_add2.module)
    s = allo.customize(Top)
    s.compose(s_add2)
    print(s.module)

    f = s.build(target="vhls")
    print(f)


def test_double_partition():
    M, N, K = 4, 4, 4

    def Linear_layer1(
        inp: float32[M, K], W: float32[K, N], B: float32[N]
    ) -> float32[M, N]:
        outp: float32[M, N] = 0.0
        for i, j in allo.grid(M, N, name="gemm"):
            for k in allo.reduction(K):
                outp[i, j] += inp[i, k] * W[k, j]
        for i, j in allo.grid(M, N, name="bias"):
            outp[i, j] += B[j]
        return outp

    def Linear_layer2(
        inp: float32[M, K], W: float32[K, N], B: float32[N]
    ) -> float32[M, N]:
        outp: float32[M, N] = 0.0
        for i, j in allo.grid(M, N, name="gemm"):
            for k in allo.reduction(K):
                outp[i, j] += inp[i, k] * W[k, j]
        for i, j in allo.grid(M, N, name="bias"):
            outp[i, j] += B[j]
        return outp

    def Add(inp1: float32[M, N], inp2: float32[M, N]) -> float32[M, N]:
        outp: float32[M, N] = 0.0
        for i, j in allo.grid(M, N, name="add"):
            outp[i, j] = inp1[i, j] + inp2[i, j]
        return outp

    def Top(inp: float32[M, K], W: float32[K, N], B: float32[N]) -> float32[M, N]:
        add1 = Linear_layer1(inp, W, B)
        add2 = Linear_layer2(inp, W, B)
        outp1 = Add(add1, add2)
        return outp1

    s_add = allo.customize(Add)
    s_add.partition(s_add.inp1, partition_type=1, dim=2, factor=2)
    s_add.partition(s_add.inp2, partition_type=1, dim=2, factor=2)
    print(s_add.module)
    s = allo.customize(Top)
    s.compose(s_add)
    f = s.build(target="vhls")
    print(f)


def test_output_partition_compose():
    M, N, K = 4, 4, 4

    def Linear_layer(
        inp: float32[M, K], W: float32[K, N], B: float32[N]
    ) -> float32[M, N]:
        outp: float32[M, N] = 0.0
        for i, j in allo.grid(M, N, name="gemm"):
            for k in allo.reduction(K):
                outp[i, j] += inp[i, k] * W[k, j]
        for i, j in allo.grid(M, N, name="bias"):
            outp[i, j] += B[j]
        return outp

    def Add(inp1: float32[M, N], inp2: float32[M, N]) -> float32[M, N]:
        outp: float32[M, N] = 0.0
        for i, j in allo.grid(M, N, name="add"):
            outp[i, j] = inp1[i, j] + inp2[i, j]
        return outp

    def Top(inp: float32[M, K], W: float32[K, N], B: float32[N]) -> float32[M, N]:
        add1 = Linear_layer(inp, W, B)
        add2 = Linear_layer(inp, W, B)
        outp1 = Add(add1, add2)
        return outp1

    s_ll = allo.customize(Linear_layer)
    s_ll.partition(s_ll.outp, partition_type=1, dim=2, factor=2)
    s = allo.customize(Top)
    s.compose(s_ll)
    print(s.module)

    f = s.build(target="vhls")
    print(f)


def test_nested_compose_partition():
    M, N = 2, 2

    def matrix_addi(A: int32[M, N]) -> int32[M, N]:
        B: int32[M, N]
        for i, j in allo.grid(M, N):
            B[i, j] = A[i, j] + 1
        return B

    s_addi = allo.customize(matrix_addi)
    s_addi.partition(s_addi.A)

    def matrix_addi_top(A: int32[M, N]) -> int32[M, N]:
        B = matrix_addi(A)
        return B

    s_addi_top = allo.customize(matrix_addi_top)
    s_addi_top.compose(s_addi)
    print(s_addi_top.module)

    def top(inp: int32[M, N]) -> int32[M, N]:
        outp = matrix_addi_top(inp)
        return outp

    s = allo.customize(top)
    # s.partition(s.inp)
    s.compose(s_addi_top)
    print(s.module)


def test_reuse_at_compose():
    def reuse_blur_x_y(A: int32[10, 10]) -> int32[8, 8]:
        B: int32[8, 8] = 0
        for y, x in allo.grid(8, 8):
            B[y, x] = A[y, x] + A[y + 1, x + 1] + A[y + 2, x + 2]
        return B

    s = allo.customize(reuse_blur_x_y)
    RB_y = s.reuse_at(s.A, "y")
    RB_x = s.reuse_at(RB_y, "x")

    def top_kernel(A: int32[10, 10]) -> int32[8, 8]:
        B = reuse_blur_x_y(A)
        return B * 2

    s_top = allo.customize(top_kernel)
    s_top.compose(s)
    mod = s_top.build()

    np_A = np.random.randint(0, 10, size=(10, 10)).astype(np.int32)
    np_C = np.zeros((8, 8), dtype="int")

    for y in range(0, 8):
        for x in range(0, 8):
            np_C[y][x] = np_A[y][x] + np_A[y + 1][x + 1] + np_A[y + 2][x + 2]
            np_C[y][x] *= 2

    np_B = mod(np_A)

    assert np.array_equal(np_B, np_C)


def test_two_reuse_at_compose():
    def blur_A(A: int32[10, 10]) -> int32[8, 8]:
        B: int32[8, 8] = 0
        for y, x in allo.grid(8, 8):
            B[y, x] = A[y, x] + A[y + 1, x + 1] + A[y + 2, x + 2]
        return B

    def blur_B(B: int32[8, 8]) -> int32[6, 6]:
        C: int32[6, 6] = 0
        for y, x in allo.grid(6, 6):
            C[y, x] = B[y, x] + B[y + 1, x + 1] + B[y + 2, x + 2]
        return C

    s0 = allo.customize(blur_A)
    RB_y = s0.reuse_at(s0.A, "y")
    RB_x = s0.reuse_at(RB_y, "x")

    s1 = allo.customize(blur_B)
    RB_y = s1.reuse_at(s1.B, "y")
    RB_x = s1.reuse_at(RB_y, "x")

    def top_kernel(A: int32[10, 10]) -> int32[6, 6]:
        B = blur_A(A)
        C = blur_B(B)
        return C

    s_top = allo.customize(top_kernel)
    s_top.compose([s0, s1])
    mod = s_top.build()
    print(s_top.module)

    np_A = np.random.randint(0, 10, size=(10, 10)).astype(np.int32)
    np_B = np.zeros((8, 8), dtype="int")
    np_C = np.zeros((6, 6), dtype="int")
    np_C_ref = np.zeros((6, 6), dtype="int")

    for y in range(0, 8):
        for x in range(0, 8):
            np_B[y][x] = np_A[y][x] + np_A[y + 1][x + 1] + np_A[y + 2][x + 2]

    for y in range(0, 6):
        for x in range(0, 6):
            np_C_ref[y][x] = np_B[y][x] + np_B[y + 1][x + 1] + np_B[y + 2][x + 2]

    np_C = mod(np_A)

    assert np.array_equal(np_C, np_C_ref)


def test_reuse_function_1():
    M, N = 2, 2

    def matrix_addi(A: int32[M, N]) -> int32[M, N]:
        B: int32[M, N]
        for i, j in allo.grid(M, N):
            B[i, j] = A[i, j] + 1
        return B

    s_addi = allo.customize(matrix_addi)
    s_addi.partition(s_addi.A)

    def matrix_subi(A: int32[M, N]) -> int32[M, N]:
        B: int32[M, N]
        for i, j in allo.grid(M, N):
            B[i, j] = A[i, j] - 1
        return B

    s_subi = allo.customize(matrix_subi)

    def top(inp: int32[M, N]) -> int32[M, N]:
        temp1 = matrix_addi(inp)
        temp2 = matrix_subi(temp1)
        outp = matrix_addi(temp2)
        return outp

    s = allo.customize(top)
    s.compose(s_addi)
    s.compose(s_subi)
    print(s.module)


def test_reuse_function_2():
    M, N = 2, 2

    def matrix_addi(A: int32[M, N]) -> int32[M, N]:
        B: int32[M, N]
        for i, j in allo.grid(M, N):
            B[i, j] = A[i, j] + 1
        return B

    s_addi = allo.customize(matrix_addi)
    # s_addi.partition(s_addi.A)

    def matrix_subi(A: int32[M, N]) -> int32[M, N]:
        B: int32[M, N]
        for i, j in allo.grid(M, N):
            B[i, j] = A[i, j] - 1
        return B

    s_subi = allo.customize(matrix_subi)
    # s_subi.partition(s_subi.B)

    def top(inp: int32[M, N]) -> int32[M, N]:
        temp1 = matrix_addi(inp)
        temp2 = matrix_subi(temp1)
        temp3 = matrix_addi(temp2)
        outp = matrix_subi(temp3)
        return outp

    s = allo.customize(top)
    s.partition(s.outp)
    s.compose(s_addi)
    s.compose(s_subi)
    print(s.module)


def test_dependent_primitives():
    def kernel(A: int32[32]):
        for i in range(32):
            A[i] = i

    def top(A: int32[32]):
        kernel(A)

    s0 = allo.customize(kernel)
    s0.split("i", factor=2)
    s0.pipeline("i.inner")
    s = allo.customize(top)
    s.compose(s0)


def test_nested_compose():
    M, K = 8, 8

    def add(A: "float32[M, K]", B: "float32[M, K]", C: "float32[M, K]"):
        for i, j in allo.grid(M, K, name="add"):
            C[i, j] = A[i, j] + B[i, j]

    def add_const[N](A: "float32[M, K]", B: "float32[M, K]", C: "float32[M, K]"):
        add(A, B, C)
        for i, j in allo.grid(M, K):
            C[i, j] = C[i, j] + N

    def top() -> "float32[M, K]":
        A: float32[M, K] = 1
        B: float32[M, K] = 2
        C: float32[M, K] = 3
        add_const[5, "const5"](A, B, C)
        add_const[7, "const7"](A, B, C)
        return C

    def schedule_add(add):
        s = allo.customize(add)
        s.pipeline("j")
        return s

    def schedule_const(add_const, N):
        add_s = schedule_add(add)
        s = allo.customize(add_const, instantiate=[N])
        s.compose(add_s)
        return s

    s_const_5 = schedule_const(add_const, 5)
    s_const_7 = schedule_const(add_const, 7)
    s = allo.customize(top)
    # only apply to one of the add_const
    s.compose(s_const_5, id="const7")
    mod = s.build(target="vitis_hls").hls_code
    assert "add_const5" in mod and "add_const_const5" in mod
    assert "add_const7" in mod and "add_const_const7" in mod
    # Count number of pipeline pragmas in the module
    # including the load/store rewind
    pipeline_count = str(mod).count("#pragma HLS pipeline II=1")
    assert pipeline_count == 2


if __name__ == "__main__":
    pytest.main([__file__])
