import Mathlib

set_option maxHeartbeats 0

namespace LeanProbe.Bench.Analysis

theorem abs_sub_le_abs_add_abs (x y : Real) : |x - y| <= |x| + |y| := by
  have h := abs_add_le x (-y)
  simpa [sub_eq_add_neg, abs_neg] using h

theorem abs_abs_sub_abs_le_abs_sub (x y : Real) : abs (abs x - abs y) <= abs (x - y) := by
  simpa using abs_abs_sub_abs_le x y

theorem dist_triangle_real (x y z : Real) : |x - z| <= |x - y| + |y - z| := by
  have h := abs_add_le (x - y) (y - z)
  have hxyz : x - y + (y - z) = x - z := by
    ring
  simpa [hxyz] using h

theorem lipschitz_abs_one (x y : Real) : abs (abs x - abs y) <= 1 * abs (x - y) := by
  simpa using abs_abs_sub_abs_le x y

theorem continuous_shifted_square (a b : Real) :
    Continuous fun x : Real => (x + a) ^ 2 + b * x := by
  fun_prop

end LeanProbe.Bench.Analysis
