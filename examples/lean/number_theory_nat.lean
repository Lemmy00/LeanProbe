import Mathlib

set_option maxHeartbeats 0

namespace LeanProbe.Bench.NumberTheory

theorem nat_add_cancel_bench (a b c : Nat) (h : a + c = b + c) : a = b := by
  omega

theorem nat_mul_pos_bench (a b : Nat) (ha : 0 < a) (hb : 0 < b) : 0 < a * b := by
  exact Nat.mul_pos ha hb

theorem nat_mod_lt_bench (n k : Nat) (hk : 0 < k) : n % k < k := by
  exact Nat.mod_lt n hk

theorem nat_square_eq_mul (n : Nat) : n ^ 2 = n * n := by
  ring

theorem nat_dvd_trans_bench (a b c : Nat) (hab : a ∣ b) (hbc : b ∣ c) : a ∣ c := by
  exact dvd_trans hab hbc

end LeanProbe.Bench.NumberTheory
