import Mathlib

set_option maxHeartbeats 0

namespace LeanProbe.Bench.Algebra

theorem sq_add_sq_nonneg (x y : Real) : 0 <= x ^ 2 + y ^ 2 := by
  nlinarith [sq_nonneg x, sq_nonneg y]

theorem two_mul_le_sq_add_sq (x y : Real) : 2 * x * y <= x ^ 2 + y ^ 2 := by
  nlinarith [sq_nonneg (x - y)]

theorem sq_sub_sq_factor (x y : Real) : x ^ 2 - y ^ 2 = (x - y) * (x + y) := by
  ring

theorem cube_add_expansion (x y : Real) :
    (x + y) ^ 3 = x ^ 3 + 3 * x ^ 2 * y + 3 * x * y ^ 2 + y ^ 3 := by
  ring

theorem square_le_self_on_unit_interval (x : Real) (hx0 : 0 <= x) (hx1 : x <= 1) :
    x ^ 2 <= x := by
  nlinarith [sq_nonneg x, sq_nonneg (1 - x)]

end LeanProbe.Bench.Algebra
