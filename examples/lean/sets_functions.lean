import Mathlib

set_option maxHeartbeats 0

open Set Function

namespace LeanProbe.Bench.Sets

theorem preimage_inter_eq {α β : Type*} (f : α → β) (s t : Set β) :
    f ⁻¹' (s ∩ t) = (f ⁻¹' s) ∩ (f ⁻¹' t) := by
  ext x
  rfl

theorem preimage_subset_preimage {α β : Type*} (f : α → β) {s t : Set β} (h : s ⊆ t) :
    f ⁻¹' s ⊆ f ⁻¹' t := by
  intro x hx
  exact h hx

theorem image_subset_of_mapsTo {α β : Type*} {f : α → β} {s : Set α} {t : Set β}
    (h : MapsTo f s t) : f '' s ⊆ t := by
  intro y hy
  rcases hy with ⟨x, hx, rfl⟩
  exact h hx

theorem injective_from_left_inverse {α β : Type*} {f : α → β} {g : β → α}
    (h : LeftInverse g f) : Injective f := by
  intro x y hxy
  exact h.injective hxy

theorem surjective_from_right_inverse {α β : Type*} {f : α → β} {g : β → α}
    (h : RightInverse g f) : Surjective f := by
  intro y
  exact ⟨g y, h y⟩

end LeanProbe.Bench.Sets
