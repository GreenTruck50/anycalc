# Tool-call notes

## `run_commands`

The full payload is one JSON object whose only key is `commands`, whose value is a
flat JSON array of complete shell command strings, written on a single line, each
entry self-contained and starting with the workspace `cd`. In the snippets below
`<ws>` is the workspace root given in the env block - never write the literal
absolute path, it embeds the machine's user name (PII):

```json
{"commands": ["cd <ws> && ls -a | head -40"]}
```

Independent commands go in the same array:

```json
{"commands": ["cd <ws> && pwd", "cd <ws> && ls -a | head -40"]}
```

No heredocs, and `commands` must be a real JSON array - never a string holding the
array text, otherwise the brackets/quotes reach the shell literally and the command
dies on shell syntax, not on anything in the command itself.

One-command-per-call also works: issue separate `run_commands` calls in the same
response, each with a single-entry array. This exact shape is verified working
(`<parent>` is the parent of `<ws>`):

```json
{"commands": ["cd <ws> && pwd"]}          -> <ws>
{"commands": ["cd <ws> && cd .. && pwd"]} -> <parent>
```

Every call starts in a fresh shell at the workspace root, so a bare `cd ..` is a
no-op - reach the parent by chaining it off the workspace `cd` in the same command
string. The `cd` prefix is never optional.

A call that ran echoes what it ran as `[{"query": "<command>", "result": ...}]`.
`✖ Invalid input` echoes nothing: the tool wrapper rejected the call against its
input schema before any shell saw it, so it is never a shell error and never about
the command text - when it starts, the identical shape that worked a moment earlier
is refused even for `pwd`, `ls` or `echo hi`. Do not keep re-quoting the payload;
carry on with the file tools (`read_files`, `search_codebase`, `editor`) and retry
`run_commands` later. The refusals come in windows.

## `dquote>` in the terminal (unbalanced quotes)

Symptom through `run_commands`: the call comes back with the not-observed-completion
error instead of a result -

```text
[Command completion could not be observed; the command may still be running and
must not be assumed to have succeeded. The terminal has been left open and will
not be closed automatically.]
The command's output could not be captured through shell integration. Here is the
current terminal's content, which may include the command's output:
```

That is usually not a slow command - it means the payload left the interactive zsh
sitting at its `dquote>` continuation prompt, waiting for a closing `"` that never
arrived. The shell never finished, so shell integration never reported completion.
Treat the "current terminal's content" it dumps as **stale scrollback** (the prompt,
earlier commands, even the login banner) and never read it as this command's output.

An unterminated quote means the command has NOT run, and anything sent after it is
swallowed as string content. Siblings of `dquote>`: `quote>` (unterminated `'`),
`bquote>` (backtick), `cmdsubst>` (open `(`). Non-interactive zsh reports the same
mistake as `zsh:1: unmatched "` instead of prompting.

Usual cause: nested quoting in a payload - e.g. `python3 -c "..."` whose body also
needs `"` - the escapes get consumed on the way to the shell and the final quote
arrives unbalanced. A single stray `"` in a long `run_commands` string is enough.

Recover: close the quote and press Enter, or Ctrl-C to abandon the line. Never
pattern-kill the shell over it (see the killing-processes rule).

Avoid: keep the shell string single-quoted and use double quotes freely inside it
(`python3 -c 'print("hi")'`). When the body needs single quotes too, write it to a
file with the `editor` tool and run the file (`python3 /tmp/x.py`) rather than
nesting escapes - heredocs are banned by this project's rules.

After this error do not assume the command ran: re-issue a trivial command (`pwd`),
confirm a clean prompt and a real result, then retry the real command with balanced
quotes - and check whether the intended effect actually happened before re-running
anything that mutates state.

