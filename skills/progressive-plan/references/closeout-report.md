# User-facing closeout report

End every closeout with a short report in this shape:

```text
Phase P2 closeout — <phase name>
Verdict: addressed | partial | blocked
Master coverage: D1 met (<evidence>), D2 partial (<gap>), D3 not started
Discoveries no earlier plan predicted: <one line each, or "none">
Plan updates: master v3 (<rows/sections changed>); P3 plan v2 (<sections changed>)
Standards: passed | <unmet rule and reason>
Commit: <short hash>
Branch: plan/<slug>
Next action: <one concrete action>
```

Lead with the verdict and the coverage result. Do not bury a partial verdict under a list of completed steps.
