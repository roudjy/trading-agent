# QRE Prior-Failure Retrieval

This surface links behavior theses to prior failures, dead zones, and prior
actions using existing local retrieval and research-memory artifacts.

Retrieval remains context only. It cannot generate executable strategies,
register strategies, promote candidates, mutate campaigns, or activate
paper/shadow/live paths.

## Summary

- Status: `ready`
- Thesis count: `7`
- Prior failure count: `1`
- Dead-zone count: `5`
- Prior action count: `1`
- Retrieval match count: `20`

## Commands

```powershell
python -m research.qre_prior_failure_retrieval --status
python -m research.qre_prior_failure_retrieval --write
```

## Capability Boundary

- automatic hypothesis proposals or campaign-seed proposals remain context
  unless separately authorized elsewhere;
- this surface does not generate executable strategy code;
- this surface does not register strategies or launch campaigns;
- retrieved prior failures remain provenance-linked context, not truth authority.

