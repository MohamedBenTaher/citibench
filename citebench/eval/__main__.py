"""``python -m citebench.eval`` delegates to the C6 CI gate."""

from citebench.eval.ci import main

raise SystemExit(main())
