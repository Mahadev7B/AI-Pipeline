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

## What is not wired yet

- **Asking the company to evaluate an idea.** This is the step that runs real
  agents and costs real money, so it is deliberately not half-built. The
  button says so rather than pretending.
- **Start work.** Sending an approved brief into the factory.

## How it is put together

- One credential. `founder_auth` is imported from `ops/control-center`, so
  there is one passphrase and one verification path, not two.
- One writer. Every write shells out to `ops/db/opsdb.py`. This process opens
  the database read-only and could not write to it if a bug tried.
- Three artifacts, never overwritten: your raw idea, each company round, and
  the approved brief. Editing appends; it never rewrites.

`seed_founder_idea.py` put the first idea in — the one that started TASK-026,
in your own words, with the two rounds it actually went through.
