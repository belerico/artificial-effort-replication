/*
 * Per-puzzle countdown. Include AFTER the game-specific JS.
 * Reads js_vars.params.puzzle_timeout (seconds). 0 or absent = disabled.
 *
 * - Shows a visible MM:SS countdown for the CURRENT puzzle; it resets every
 *   time a new puzzle loads (this is the only timer on the page — oTree's
 *   page-level timeout is disabled in get_timeout_seconds()).
 * - When it reaches 0: freezes the UI, sends {type:'timeout'} to the server;
 *   the server marks the puzzle TIMEOUT and the JS auto-advances.
 */
(function () {
    if (typeof liveSend === 'undefined') return;

    var _timer = null;
    var _interval = null;
    var _deadline = 0;
    var _movingForward = false;
    var _serverIter = 0;
    var _origNewPuzzle = newPuzzle;
    var _origLiveRecv = liveRecv;
    var _origMoveForward = moveForward;

    // Inject a visible countdown at the top of the task area.
    var _display = document.createElement('div');
    _display.id = 'puzzle-timer';
    _display.style.cssText =
        'font-weight:bold;font-size:1.2rem;text-align:center;margin:0.25rem 0 0.75rem;';
    var _host = document.querySelector('.task-wrapper') || document.body;
    _host.insertBefore(_display, _host.firstChild);

    // Widen the answer box so the full placeholder hint is visible. oTree's
    // theme2.css caps it (.input-group → 400px, input[type=number] → 150px);
    // inline styles override that. Done here because this script loads on
    // every game page and oTree Lite has no project-wide stylesheet hook.
    var _question = document.querySelector('.task-question');
    if (_question) {
        _question.style.width = '40rem';
        _question.style.maxWidth = '95vw';
    }
    var _answer = document.querySelector('.task-input');
    if (_answer) {
        _answer.style.maxWidth = 'none';  // let the field flex to fill the group
    }

    // Admin "Skip puzzle" button — only when the session config sets allow_skip.
    // Clicking it asks the server to skip the current puzzle and advance.
    if ((js_vars.params || {}).allow_skip) {
        var _skip = document.createElement('button');
        _skip.type = 'button';
        _skip.id = 'skip-btn';
        _skip.textContent = 'Skip puzzle';
        _skip.className = 'btn btn-outline-warning btn-sm';
        _skip.style.cssText = 'display:block;margin:0.5rem auto;';
        _skip.onclick = function () {
            if (typeof isFrozen !== 'undefined' && isFrozen) return;
            liveSend({type: 'skip'});
        };
        if (_question) {
            _question.parentNode.insertBefore(_skip, _question.nextSibling);
        } else {
            (document.querySelector('.task-wrapper') || document.body).appendChild(_skip);
        }
    }

    function _fmt(secs) {
        secs = Math.max(0, Math.round(secs));
        var m = Math.floor(secs / 60);
        var s = secs % 60;
        return m + ':' + (s < 10 ? '0' : '') + s;
    }

    function _render() {
        _display.textContent =
            'Time left for this puzzle: ' + _fmt((_deadline - Date.now()) / 1000);
    }

    function _stopInterval() {
        if (_interval) { clearInterval(_interval); _interval = null; }
    }

    function _clearTimer() {
        if (_timer) { clearTimeout(_timer); _timer = null; }
        _stopInterval();
    }

    function _startTimer() {
        _clearTimer();
        var timeout = (js_vars.params || {}).puzzle_timeout || 0;
        if (timeout <= 0) { _display.textContent = ''; return; }
        _deadline = Date.now() + timeout * 1000;
        _render();
        _interval = setInterval(_render, 1000);
        _timer = setTimeout(function () {
            _timer = null;
            _stopInterval();
            _display.textContent = "Time's up.";
            setFrozen(true);
            lockInput();
            liveSend({type: 'timeout'});
        }, timeout * 1000);
    }

    // Wrap newPuzzle: reset state, run original, (re)start the countdown
    newPuzzle = function (data) {
        _clearTimer();
        _movingForward = false;
        setFrozen(false);
        _origNewPuzzle(data);
        _startTimer();
    };

    // Wrap moveForward: guard against double-move
    moveForward = function (wait) {
        if (_movingForward) return;
        _movingForward = true;
        _origMoveForward(wait);
    };

    // Wrap liveRecv: clear timer on feedback, auto-advance on timeout
    liveRecv = function (message) {
        if (message.type === 'feedback') _clearTimer();
        if ('progress' in message) _serverIter = message.progress.iteration;

        // Timeout feedback: skip puzzle_delay, advance immediately
        if (message.type === 'feedback' && message.timed_out) {
            showFeedback(message);
            if ('progress' in message) showProgress(message.progress);
            moveForward(0);
            return;
        }

        _origLiveRecv(message);
    };

    // Override submitAnswer: attach iteration for stale-answer protection
    submitAnswer = function () {
        if (isFrozen || input.value === "") return;
        lockInput();
        resetFeedback();
        liveSend({type: 'answer', answer: input.value, iteration: _serverIter});
    };
})();
