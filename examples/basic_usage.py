from lean_probe import LeanProbe


def main() -> None:
    probe = LeanProbe()
    result = probe.proof_state_from_code("theorem ex (n : Nat) : n = n := by sorry")
    print(result)
    proof_state = result["sorries"][0]["proof_state"]
    print(probe.tactic_step(result["session_id"], proof_state, "rfl"))
    probe.close()


if __name__ == "__main__":
    main()
