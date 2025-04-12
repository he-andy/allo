# Copyright Allo authors. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from allo.ir.utils import MockBuffer
import numpy as np
import pytest
from allo.ir.types import float32, int32
from allo.autoscheduler.passes import dataflow_optimization_pass, DEBUG_POINTS
from tests.autoscheduler.polybench import get_polybench
import allo
from allo.backend.hls import is_available

kinds = [
    "graph",
    # "node",
    # "combined"
]


@pytest.mark.parametrize("debug_point", DEBUG_POINTS)
@pytest.mark.parametrize("kind", kinds)
def test_simple(debug_point, kind):
    def simple() -> int32[10, 10]:
        def stageA() -> int32[10, 10]:
            A: int32[10, 10]
            for j in range(10):
                for i in range(10):
                    A[i, j] = i + j
            return A

        def stageB(A: int32[10, 10]) -> int32[10, 10]:
            B: int32[10, 10]
            for i in range(10):
                for j in range(10):
                    B[i, j] = A[i, j] + 1
            return B

        A = stageA()
        B = stageB(A)
        return B

    s = allo.customize(simple)
    optimized_schedule = dataflow_optimization_pass(
        s, debug_point=debug_point, kind=kind
    )

    mod = (
        optimized_schedule.build()
        if debug_point is not None
        else optimized_schedule.build(target="vitis_hls")
    )

    expected = np.zeros((10, 10))
    for i in range(10):
        for j in range(10):
            expected[i, j] = i + j + 1

    if debug_point is not None or is_available("vitis_hls"):
        np.testing.assert_allclose(mod(), expected)


@pytest.mark.parametrize("debug_point", DEBUG_POINTS)
@pytest.mark.parametrize("kind", kinds)
def test_three_mm(debug_point, kind):
    schedule, inputs, expected = get_polybench(
        "three_mm", size="small", concrete_type=float32
    )
    optimized_schedule = dataflow_optimization_pass(
        schedule, debug_point=debug_point, kind=kind
    )
    mod = (
        optimized_schedule.build()
        if debug_point is not None
        else optimized_schedule.build(target="vitis_hls")
    )

    if debug_point is not None or is_available("vitis_hls"):
        actual = mod(*inputs)
        np.testing.assert_allclose(actual, expected, rtol=1e-5, atol=1e-5)


@pytest.mark.parametrize("debug_point", DEBUG_POINTS)
@pytest.mark.parametrize("kind", kinds)
def test_two_mm(debug_point, kind):
    schedule, inputs, expected = get_polybench(
        "two_mm", size="small", concrete_type=float32
    )
    optimized_schedule = dataflow_optimization_pass(
        schedule, debug_point=debug_point, kind=kind
    )
    mod = (
        optimized_schedule.build()
        if debug_point is not None
        else optimized_schedule.build(target="vitis_hls")
    )

    if debug_point is not None or is_available("vitis_hls"):
        actual = mod(*inputs)
        np.testing.assert_allclose(actual, expected, rtol=1e-5, atol=1e-5)


@pytest.mark.parametrize("debug_point", DEBUG_POINTS)
@pytest.mark.parametrize("kind", kinds)
def test_atax(debug_point, kind):
    schedule, inputs, expected = get_polybench(
        "atax", size="small", concrete_type=float32
    )
    optimized_schedule = dataflow_optimization_pass(
        schedule, debug_point=debug_point, kind=kind
    )
    mod = (
        optimized_schedule.build()
        if debug_point is not None
        else optimized_schedule.build(target="vitis_hls")
    )

    if debug_point is not None or is_available("vitis_hls"):
        A, x, y = inputs
        y_out = np.zeros_like(y)
        mod(A, x, y_out)
        np.testing.assert_allclose(y_out, expected, rtol=1e-5, atol=1e-5)


# @pytest.mark.parametrize("debug_point", DEBUG_POINTS)
# def test_bicg(debug_point):
#     schedule, inputs, expected = get_polybench(
#         "bicg", size="small", concrete_type=float32
#     )
#     optimized_schedule = dataflow_optimization_pass(schedule, debug_point=debug_point)
#     mod = optimized_schedule.build()

#     A, A_copy, s, q, p, r = inputs
#     q_out = np.zeros_like(q)
#     s_out = np.zeros_like(s)
#     mod(A, A_copy, p, r, q_out, s_out)

#     expected_q, expected_s = expected
#     np.testing.assert_allclose(q_out, expected_q)
#     np.testing.assert_allclose(s_out, expected_s)


@pytest.mark.parametrize("debug_point", DEBUG_POINTS)
@pytest.mark.parametrize("kind", kinds)
def test_gemm(debug_point, kind):
    schedule, inputs, expected = get_polybench(
        "gemm", size="small", concrete_type=float32
    )
    optimized_schedule = dataflow_optimization_pass(
        schedule, debug_point=debug_point, kind=kind
    )
    mod = (
        optimized_schedule.build()
        if debug_point is not None
        else optimized_schedule.build(target="vitis_hls")
    )

    if debug_point is not None or is_available("vitis_hls"):
        A, B, C = inputs
        output = np.zeros_like(expected)
        mod(A, B, C, output)
        np.testing.assert_allclose(output, expected, rtol=1e-5, atol=1e-5)


@pytest.mark.parametrize("debug_point", DEBUG_POINTS)
@pytest.mark.parametrize("kind", kinds)
def test_gesummv(debug_point, kind):
    schedule, inputs, expected = get_polybench(
        "gesummv", size="small", concrete_type=float32
    )
    optimized_schedule = dataflow_optimization_pass(
        schedule, debug_point=debug_point, kind=kind
    )

    mod = (
        optimized_schedule.build()
        if debug_point is not None
        else optimized_schedule.build(target="vitis_hls")
    )

    if debug_point is not None or is_available("vitis_hls"):
        A, B, x = inputs
        y = np.zeros_like(expected)
        mod(A, B, x, y)
        np.testing.assert_allclose(y, expected, rtol=1e-5, atol=1e-5)


# @pytest.mark.parametrize("debug_point", DEBUG_POINTS)
# def test_mvt(debug_point):
#     schedule, inputs, expected = get_polybench(
#         "mvt", size="small", concrete_type=float32
#     )
#     optimized_schedule = dataflow_optimization_pass(schedule, debug_point=debug_point)
#     mod = optimized_schedule.build()

#     A, A_copy, y1, y2, x1, x2, x1_out, x2_out = inputs
#     expected_x1, expected_x2 = expected
#     out_x1 = np.zeros_like(x1)
#     out_x2 = np.zeros_like(x2)
#     mod(A, A_copy, y1, y2, x1, x2, out_x1, out_x2)

#     np.testing.assert_allclose(out_x1, expected_x1, rtol=1e-5, atol=1e-5)
#     np.testing.assert_allclose(out_x2, expected_x2, rtol=1e-5, atol=1e-5)


if __name__ == "__main__":
    pytest.main([__file__])
