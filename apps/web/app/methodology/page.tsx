import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Methodology - Litmuz',
  description:
    'How Litmuz verifies research claims: atomic decomposition, deterministic citation checks against the primary literature, evidence-grounded entailment, a safety gate, and human review.',
};

export default function MethodologyPage() {
  return (
    <main className="narrow prose">
      <p className="brand">Methodology</p>
      <h1>How Litmuz reaches a verdict</h1>
      <p className="muted lede">
        Litmuz checks a research memo one claim at a time, against the primary literature. It is
        built to be honest about what it cannot confirm: it triages and flags, and it never
        certifies a claim on its own. Every verdict is traceable to the evidence behind it.
      </p>

      <h2>The pipeline</h2>
      <ol className="method-steps">
        <li>
          <h3>Decomposition</h3>
          <p>
            The memo is split into atomic claims - one independently checkable proposition each -
            with their citations attached. A claim is only as trustworthy as the smallest statement
            it can be reduced to, so we check the smallest statements.
          </p>
        </li>
        <li>
          <h3>Deterministic citation check</h3>
          <p>
            Every citation is resolved against the primary literature - PubMed, PMC, and Crossref -
            by rule, not by a language model. A fabricated identifier, a retracted or
            corrected-for-concern source, or metadata that does not match the claim is caught here
            and can never be argued away downstream.
          </p>
        </li>
        <li>
          <h3>Evidence and entailment</h3>
          <p>
            We retrieve the cited source text (and, where a claim is under-supported, related
            literature) and assess whether that evidence actually entails the claim. A supported
            verdict must quote the specific sentence it relied on; when the evidence is not there,
            we say so rather than inventing it.
          </p>
        </li>
        <li>
          <h3>Classification and the safety gate</h3>
          <p>
            Each claim is classified, and anything safety-critical - a target, a dose, an
            indication - is held to a stricter standard. A safety-critical claim can never
            auto-pass, by design; it is always routed to a human, even when the evidence looks
            supportive.
          </p>
        </li>
        <li>
          <h3>Human review</h3>
          <p>
            Claims that are flagged, unresolved, or safety-critical land in a review queue with
            their full evidence trail, so a person makes the final call. Litmuz narrows the work; it
            does not replace the reviewer.
          </p>
        </li>
      </ol>

      <h2>The verdict</h2>
      <p>Each claim carries a traffic-light verdict and a diagnostic code you can audit:</p>
      <ul className="method-verdicts">
        <li>
          <span className="verdict-badge verdict-success">Grounded</span>
          <span>The claim is supported by evidence we could locate and quote.</span>
        </li>
        <li>
          <span className="verdict-badge verdict-warning">Needs review</span>
          <span>
            Unverifiable or under-supported - the evidence was not located, or the claim is
            safety-critical - and routed to a human.
          </span>
        </li>
        <li>
          <span className="verdict-badge verdict-danger">Flagged</span>
          <span>Contradicted by the evidence, or built on a fabricated or retracted citation.</span>
        </li>
      </ul>

      <h2>What we stand on</h2>
      <ul className="method-principles">
        <li>
          <strong>Honest negatives.</strong> A claim that cannot be confirmed is never quietly
          presented as if it were. Yellow and red are first-class outcomes, not failures.
        </li>
        <li>
          <strong>Safety first.</strong> Safety-critical claims cannot auto-pass, full stop.
        </li>
        <li>
          <strong>Grounded in the primary literature.</strong> Verdicts come from real sources and
          the exact sentences within them, not from a model&#39;s recollection.
        </li>
        <li>
          <strong>Auditable.</strong> Every verdict links to the citation status, the evidence, and
          the reasoning, so it can be checked and overridden.
        </li>
      </ul>

      <h2>What we do not publish</h2>
      <p className="muted">
        The verdicts and their evidence are meant to be fully transparent to you. The recipe behind
        them - the exact prompts, thresholds, model configuration, and internal tooling - is not,
        both to protect the method and to keep it from being gamed. If you need deeper assurance for
        a specific use, we are happy to walk a qualified reviewer through it under agreement.
      </p>
    </main>
  );
}
