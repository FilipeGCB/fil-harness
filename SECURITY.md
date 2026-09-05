# Security Policy

## Security-relevant behavior

Reports are especially useful when they demonstrate one of these failures:

- a provider can self-approve a candidate;
- provider-controlled text is accepted as trusted evidence;
- evidence for one candidate can approve another candidate;
- a policy `DENY` can be bypassed;
- an unknown capability becomes authorized;
- the writable workspace can silently redefine the trusted verification authority for the same run;
- private or secret material is exposed by the public distribution.

## Boundaries

The Harness controls authority and verification flow. It does not claim to provide:

- isolation against a compromised host or administrator;
- a hardened sandbox for arbitrary hostile code;
- cryptographic software-supply-chain attestation;
- proof that existing tests are sufficient to find every defect;
- automatic regulatory or compliance certification.

When verification, evidence, policy classification, or execution outcome is ambiguous, the safe direction is to stop rather than authorize.
