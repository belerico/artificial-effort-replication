Replication package for "Artificial Effort"
===========================================

Federico Belotti, Stefano Coniglio, Antonio Cosma, Francesco Fallucchi
University of Bergamo, Italy

Overview
--------

This package reproduces every figure, table and number reported in the paper
from two SQLite databases: the LLM benchmark (data/results_llm.db) and the human
benchmark (data/results_human.db). Four Python scripts in analysis/ produce the
11 figures, Tables 2, 3, 5 and 6, and the numbers quoted in the text. Tables 1
and 4 are descriptive and contain no estimates (see "List of tables and
figures"). The code that collected both data sets is in collection/, together
with the browser-automation script whose core is Listing 1 of the paper.
Running all analysis scripts takes under a minute on a laptop.


Data availability and provenance
--------------------------------

All data were collected by the authors, who hold the rights to distribute them.
Code and data are released under the MIT License (LICENSE).

Summary of availability: all data used in the paper are publicly available in
this package. The only information withheld is the correspondence between the
participants' email addresses and their anonymized ids, which no analysis uses.

LLM benchmark (data/results_llm.db). Between 18 and 26 March 2026 we queried 23
LLMs through the OpenRouter API on the eight real-effort tasks, in five
treatments (T0 control, T1-T4 persona x verbal incentive), 20 trials per model,
task and treatment, with the runner in collection/real_effort/run_benchmarks.py.
The database contains every trial of these five treatments, as recorded by the
runner.

Model metadata (Table 4). The release dates and the input and output prices
(USD per million tokens) of the 23 models are those reported by the OpenRouter
API (OpenRouter, 2026) on 23 March 2026. They are written into the analysis
code (prices: analysis/common.py, PRICING; release dates:
analysis/make_figures.py, MODEL_RELEASE_TS), so the analysis needs no internet
access. Prices listed by OpenRouter today may differ.

Human benchmark (data/raw/human/, data/results_human.db). Lab experiment with
university students at the University of Bergamo, run with oTree
(collection/real_effort/), 10 trials per task:
  Day 1, 19 May 2026, five tasks: oTree sessions 0ws12wu7 (33 participants,
         07:08-08:10 UTC) and 3j1bdljm (3 participants, 08:32-09:19 UTC),
         36 participants in total;
  Day 2, 21 May 2026, three tasks: oTree session 912oggcm (39 participants,
         07:41-08:44 UTC), 33 of the Day-1 participants and 6 new ones.
The times are those of the first puzzle shown and of the last answer submitted
in each session (experiments.created_at and experiments.completed_at in
data/results_human.db). In total 42 distinct people took part, and all of them
are included in the analysis.

Payment. Participants received a show-up fee of EUR 5 for each session
attended. In addition, in each session one task was drawn at random, and
participants earned a bonus of EUR 0.50 for each correct trial in that task.
The draw and the payments were made by the experimenters at payment time,
outside oTree (the oTree code never sets a payoff: payoff_summary in
collection/real_effort/config/__init__.py).

The project was approved by the Committee for the Integrity and Ethics of
Research of the University of Bergamo (Ref. 2026_06_07). Participants entered
an email address to be paid; before publication every email was replaced by an
anonymized id (001-046). The email-id correspondence is kept by the authors and
is not distributed. Three participants typed a different email on each day and
therefore have two ids in the raw files; data/results_human.db links them
(see analysis/build_results_human.py).


Dataset list
------------

data/results_llm.db                   LLM benchmark, one row per trial (SQLite)
data/results_human.db                 human benchmark, one row per trial (SQLite),
                                      built from the raw files below
data/raw/human/day-1/<task>_custom_export_2026-05-19.csv
data/raw/human/day-2/<task>_custom_export_2026-05-21.csv
                                      raw oTree trial-level exports, anonymized
                                      (8 files, one per task)

All files are in open formats (SQLite 3 and CSV).

Both databases have the same three tables:
  experiments  one row per treatment (LLM) or oTree session (human)
  runs         one row per model x task (LLM) or participant x task (human)
  puzzles      one row per trial
joined by runs.experiment_id = experiments.id and puzzles.run_id = runs.id.

Variables of data/results_llm.db

  experiments
    id, name          treatment: t0-control, t1-standard-no-incentive,
                      t2-standard-incentive, t3-human-no-incentive,
                      t4-human-incentive
    created_at        UTC time the treatment was set up (dates of the trials
                      are in runs.started_at and runs.completed_at)
    completed_at, status   runner bookkeeping (not used)
    config            JSON with the settings of the treatment: models, tasks,
                      temperature, max_tokens, reasoning_effort, per-task
                      parameters, persona and incentive text
  runs
    model             OpenRouter model id (e.g. openai/gpt-5.4)
    game              task: add_numbers (Addition), task_summation (Pair
                      Summation), task_decoding (Letter Decoding),
                      task_sequences (Sequence Completion), task_transcription
                      (Distorted Text), string_entry (String Entry),
                      counting_zeros (Counting Zeros), sudoku_game (Sudoku)
    status            completed for every run
    started_at, completed_at   UTC timestamps of the run
    prompt_tokens, completion_tokens, total_tokens   tokens summed over trials
    num_correct, num_failed, num_trials   correct, incorrect and total trials
    session_time      wall-clock seconds taken by the run
    retries, error, exit_code, data_missing, session_code   runner bookkeeping
    is_text           0: the puzzle was sent as an image (all runs)
  puzzles
    iteration         trial number within the run (1-20)
    solution          correct answer
    response          the model's answer (text after "Answer:" in its reply);
                      TIMEOUT if the model did not answer within 120 seconds
    reasoning_content, reasoning_tokens   reasoning returned by the provider
    is_correct        1 if the task's checker accepts the response (the
                      is_correct function of the task module; e.g. for Pair
                      Summation any pair that sums to the target), else 0
    response_time     seconds
    prompt_tokens, completion_tokens, total_tokens   tokens of the trial

Variables of data/results_human.db

  experiments
    name              oTree session code
    day               study day (1 or 2)
    created_at, completed_at   UTC time of the first puzzle shown and of the
                      last answer submitted in the session
  runs
    participant_id    anonymized id, one per person
    participant_label anonymized id as in the raw files (differs from
                      participant_id only for the three linked participants)
    participant_code  oTree participant code (one per session)
    game              task, as in results_llm.db
    incentive         1: the bonus per correct answer was announced
    num_correct, num_failed, num_trials   participant's counters for the task
  puzzles
    iteration         trial number within the run (1-10)
    attempts          answers submitted for the trial (at most 1)
    text              puzzle content as generated by oTree
    solution, response, is_correct   as in results_llm.db; is_correct is NULL
                      when no answer was submitted
    timestamp         Unix time (UTC) the puzzle was shown
    response_timestamp   Unix time (UTC) the answer was submitted
    response_time     seconds between the two

The raw CSV files have one row per trial and the columns session_code,
participant_code, participant_label (anonymized id), incentive, num_correct,
num_failed, num_trials, iteration, attempts, text, solution, response,
is_correct, timestamp, response_timestamp, response_time, with the meanings
above. The raw Day-2 Sudoku file also contains one row with id 007 (oTree
participant code nesqagkb): the experimenter checking the session before it
started (one Sudoku trial shown, no answer submitted, no other task). It is not
a participant and is left out of data/results_human.db.


Computational requirements
--------------------------

Software: Python 3.12 and the packages pinned in pyproject.toml and uv.lock
(pandas 3.0.1, numpy 2.4.3, scipy 1.17.1, statsmodels 0.14.6, matplotlib
3.10.8, seaborn 0.13.2), installed with uv (https://docs.astral.sh/uv/). The
command "uv sync" installs the whole pinned environment. The data collection
uses the additional dependency group "collection" (oTree 6.0.11, openai
2.24.0, Playwright 1.64.1, pillow 12.1.1, py-sudoku 2.0.0, pyyaml 6.0.3); the
browser-automation script also needs Google Chrome.

Hardware: the analysis was last run on 5 November 2026 on an Apple M3 computer
(8 cores, 16 GB of RAM, macOS 26.6.2). No internet access is needed for the
analysis.

Controlled randomness: no pseudo-random generator is used in the analysis.
Every analysis script is deterministic: re-running them reproduces the tables
and output/numbers_in_text.txt exactly, and the figure PDFs differ from the
provided ones only in their embedded creation date. The data collection is
random: the puzzles are generated with Python's random module without a fixed
seed, and LLM outputs are stochastic. Collecting new data (which for the LLMs
requires a paid OpenRouter API key) therefore gives different trials and
answers on every run. The databases store the solutions and answers of the
reported trials and, for the human sessions, the puzzle content.

Time to reproduce: under 10 minutes. The four analysis scripts take about 10
seconds in total on the machine above, plus the time "uv sync" needs to
download and install the environment.

Storage: about 35 MB for the package, plus about 260 MB for the Python
environment of the analysis.


Description of programs
-----------------------

analysis/common.py              paths, task labels, LLM prices, and the loaders of
                                both databases (shared by all scripts)
analysis/build_results_human.py rebuilds data/results_human.db from the raw CSV
                                files (already provided; optional)
analysis/make_figures.py        the 11 figures -> output/figures/*.pdf
analysis/table_llm_vs_human.py  Tables 2 and 3 -> output/tables/tab_lm_llm_hum.csv,
                                tab_avg_llm_hum.csv
analysis/table_incentives.py    Tables 5 and 6 -> output/tables/tab_fixed_eff.csv,
                                tab_marg_eff.csv
analysis/numbers_in_text.py     every number quoted in the text, next to the value
                                printed in the paper -> output/numbers_in_text.txt

collection/real_effort/         oTree project used for the human sessions and the
                                task generators used for the LLM benchmark
  settings.py                   oTree sessions: real_effort_day1, real_effort_day2
  intro/                        welcome page (payment rules, email field)
  <task>/                       one oTree app per task: puzzle generator, pages
                                and participant instructions (instructions.html)
  config/otree_config.yaml      task parameters of the human sessions
  config/benchmark_config_llm.yaml  models, sampling and task parameters of the
                                LLM benchmark
  run_benchmarks.py             LLM runner: generates the trials, queries the
                                models through OpenRouter, scores the answers and
                                writes the database
  run_parallel.sh               runs run_benchmarks.py for several models in
                                parallel
  playthrough.py                browser-automation script (Playwright): plays a
                                participant's oTree session from the welcome
                                page to the last page. With --llm it answers
                                every puzzle with an LLM through OpenRouter;
                                this mode is the one shown in Listing 1 of the
                                paper. Not used to produce any result.

The experimental instructions were written and shown in English: the welcome
page (collection/real_effort/intro/Welcome.html) and one instruction page per
task (collection/real_effort/<task>/instructions.html).


Instructions to replicators
---------------------------

From the repository root:

  uv sync                                         # install the pinned environment
  uv run python analysis/make_figures.py
  uv run python analysis/table_llm_vs_human.py
  uv run python analysis/table_incentives.py
  uv run python analysis/numbers_in_text.py

Optional: uv run python analysis/build_results_human.py rebuilds
data/results_human.db from data/raw/human/ and gives an identical database.

To run the data collection (not needed to replicate the results):

  uv sync --group collection
  cd collection/real_effort
  uv run otree devserver                          # human experiment, http://localhost:8000
  export OPENROUTER_API_KEY=...
  uv run python run_benchmarks.py --help          # LLM benchmark
  uv run python playthrough.py <participant URL> --llm
                                                  # browser automation; the
                                                  # docstring of playthrough.py
                                                  # shows how to get the URL


List of tables and figures
--------------------------

The provided code reproduces all numbers in the text and all tables and figures
in the paper.

Figure 1   fig:task_difficulty          make_figures.py   fig3_t0_task_difficulty.pdf
Figure 2   fig:family_evolution         make_figures.py   fig_accuracy_by_tier.pdf
Figure 3   fig:heatmap                  make_figures.py   fig1_t0_accuracy_heatmap_human.pdf
Figure 4   fig:bubble                   make_figures.py   fig9_t0_bubble_chart.pdf
Figure 5   fig:net_gain                 make_figures.py   fig_t0_net_gain_avg.pdf
Figure 6   fig:incentive_heatmaps_standard  make_figures.py  fig_appendix_incentive_heatmap_standard.pdf
Figure 7   fig:incentive_heatmaps_human     make_figures.py  fig_appendix_incentive_heatmap_human.pdf
Figure 8   fig:heatmap_t1               make_figures.py   fig_appendix_heatmap_t1.pdf
Figure 9   fig:heatmap_t2               make_figures.py   fig_appendix_heatmap_t2.pdf
Figure 10  fig:heatmap_t3               make_figures.py   fig_appendix_heatmap_t3.pdf
Figure 11  fig:heatmap_t4               make_figures.py   fig_appendix_heatmap_t4.pdf
Table 1    tab:tasks                    descriptive (task definitions), no data
Table 2    tab:lm_llm_hum               table_llm_vs_human.py   tab_lm_llm_hum.csv
Table 3    tab:avg_llm_hum              table_llm_vs_human.py   tab_avg_llm_hum.csv
Table 4    tab:LLMs                     model metadata from the OpenRouter API
                                        (23 March 2026): prices in
                                        analysis/common.py (PRICING), release
                                        dates in analysis/make_figures.py
                                        (MODEL_RELEASE_TS)
Table 5    tab:fixed_eff                table_incentives.py     tab_fixed_eff.csv
Table 6    tab:marg_eff                 table_incentives.py     tab_marg_eff.csv
Listing 1  lst:pipeline                 code, no data: core of
                                        collection/real_effort/playthrough.py
Numbers in the text                     numbers_in_text.py      numbers_in_text.txt


References
----------

Belotti, F., Coniglio, S., Cosma, A., and Fallucchi, F. (2026). Replication
package for "Artificial Effort". Zenodo,
https://doi.org/10.5281/zenodo.24011866.

Chen, D. L., Schonger, M., and Wickens, C. (2016). oTree - An open-source
platform for laboratory, online, and field experiments. Journal of Behavioral
and Experimental Finance, 9, 88-97.

Microsoft (2020). Playwright for Python.
https://github.com/microsoft/playwright-python

OpenRouter (2026). Models API, https://openrouter.ai/api/v1/models, accessed
23 March 2026.
