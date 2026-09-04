# Idea Desk

Your ideas, before they become work. Its own program, on its own port, so
opening it shows your ideas and nothing else.

## Run it

```
python3 ops/idea-desk/server.py
```

Then open **http://127.0.0.1:8421/** and sign in with your Control Center
passphrase. The factory Control Center is a separate program on port 8420;
neither needs the other running.

## What it does today

- Write an idea in your own words and save it. Saving starts nothing and
  costs nothing.
- Open an idea and read the company's evaluation: ten concise answers, each
  expandable, then the six-field Company View and its recommendation.
- **Correct us** when the company misread you, **Edit my idea** when you want
  to change what you said, **Not building this** to park or drop it, and
  **Approve brief** to freeze a round as the source of truth.
- Approve appears only when the company's own recommendation is *Proceed* or
  *Proceed with narrowed scope*. There is no approve-anyway path — that rule
  is enforced in `opsdb.py`, not just hidden in the page.

- **Ask the company to evaluate it.** The Chief of Staff picks who should
  read this particular idea and how deep to go, those roles read it
  separately, and the Chief of Staff writes the single answer you see. Takes a
  few minutes and spends real money — the only thing here that does, and it
  says so before you click.
- **Correct us** re-runs the evaluation with your note. Your words are not
  changed; the note is stored beside them.

## Testing without spending anything

Rehearsal mode runs the whole journey — save, evaluate, read the ten answers,
correct, park, reopen — with **no model call and no cost at all**:

```
Windows      :  $env:IDEA_DESK_REHEARSAL = "1";  python ops\idea-desk\server.py
macOS/Linux  :  IDEA_DESK_REHEARSAL=1 python3 ops/idea-desk/server.py
```

The startup line and the ideas list both say `REHEARSAL MODE`, the disclosure
before evaluating says it costs nothing instead of warning you about money, and
every round it produces is labelled a rehearsal on the page and in the list.
The answers are visibly placeholders — it never pretends to be the company's
opinion. **A brief cannot be approved from a rehearsal round**; the database
refuses it, not just the page.

Start the server without that variable and you are back to real evaluations.

## What is not wired yet

- **Start work.** Sending an approved brief into the factory.

## Requirements for evaluation

Evaluating needs the `claude` command available on this machine. Everything
else — writing ideas, reading past evaluations, approving, parking — works
without it, and if it is missing the Idea Desk says so plainly instead of
failing strangely.

## How it is put together

- One credential. `founder_auth` is imported from `ops/control-center`, so
  there is one passphrase and one verification path, not two.
- One writer. Every write shells out to `ops/db/opsdb.py`. This process opens
  the database read-only and could not write to it if a bug tried.
- Three artifacts, never overwritten: your raw idea, each company round, and
  the approved brief. Editing appends; it never rewrites.

`seed_founder_idea.py` put the first idea in — the one that started TASK-026,
in your own words, with the two rounds it actually went through.
