"""pedal.benchtest — the on-demand bench test page on the Core host.

Started from the workstation by `scripts/benchtest` (`sudo systemctl start pedal.benchtest`), it
serves one page on port 47820: a block diagram of the pedal as it is built, a list of benchtests
underneath, and a lamp on each block and each test saying how the last two runs that exercised it
went. Health benchtests read `pedal-diag --json`; noise benchtests mute the engine, record, and hand
the numbers to the workstation's helper for the spectrum. It is not a second diagnostic engine.

    catalog   the benchtests, the modules, the pass bars and which module each failure paints
    lamps     the run history and the lamp rule
    helper    the job queue the workstation helper long-polls
    runner    one run: the order, the setup instructions, the codec gate
    real      the benchtests that touch the pedal
    fakes     the same benchtests with queued outcomes, for --fake
    server    the HTTP side: the token, the routes, the idle timer, shutdown
    main      the command line
"""

VERSION = "0.1"
