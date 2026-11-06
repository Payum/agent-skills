# Capabilities and metadata

An application builds its "add a payment method" screen, its refund button and its currency picker from
what the gateway class says about itself. Get it right from the code and the PSP's documentation, never
from what the PSP probably supports.

## Capabilities

`Payum\Core\Gateway\Capability` has two kinds of case.

**Derived from `handlers()`. Never declare these.** `Authorize`, `Cancel`, `Capture`, `Payout`, `Refund`,
`Sync`, and `Webhooks` (from a notify handler). A gateway has them exactly when it lists the handler.

**Declared with `DeclaresCapabilities::capabilities()`.** Each needs evidence. Look for it in this order:
the 1.x code and its tests, then the PSP's API reference. Record the evidence in the assessment.

| Capability | Declare it when | Evidence in 1.x code |
| :--- | :--- | :--- |
| `PartialCapture` | The PSP captures less than the authorized amount | a capture/do-capture request sends an amount taken from the request or details, not always the total; a `DoCapture` with `AMT`; a "complete type" flag |
| `PartialRefund` | The PSP refunds less than the captured amount | the refund request sends an amount field (`refund_amount`, `AMT`, `amount`) that can differ from the total |
| `MultiCurrency` | One account takes payments in more than one currency | the currency is sent per payment from the payment's currency code, and the PSP docs list several currencies per account |
| `Recurring` | The gateway can set up repeat charges | recurring profile, billing agreement, subscription, plan or "AutoPay" actions |
| `StoredPaymentMethods` | The gateway can charge a saved card or account later | customer, token, reference-transaction or agreement actions |
| `ThreeDSecure` | The gateway runs 3-D Secure itself | 3DS/ACS redirects, `PaReq`/`MD` fields, a challenge flow |

Rules:

- Declare a capability for what the ported gateway does, not only what the PSP offers. If the PSP supports
  partial refunds but the 1.x code always refunds the full amount, either port the partial path (and
  declare it) or leave it undeclared, and say which in the assessment.
- If a handler cannot do what a command asks (a partial refund at a PSP without them), throw a
  `Payum\Core\Exception\LogicException` from the handler rather than silently refunding the full amount.
  Payum does not enforce capabilities.
- Ship a sync handler only if the PSP can report a payment's state. Ship a cancel handler only for an
  operation that really calls something off at the PSP.
- Run `scripts/check_gateway.php`: it prints the full capability list and fails when a declared one
  repeats a derived one.

## Metadata

The gateway class takes no constructor arguments and returns the same metadata for every merchant.

| Method | What to return | How to check it |
| :--- | :--- | :--- |
| `name()` | The PSP's product name as the PSP writes it, plus the product when the package has several gateways ("PayPal Express Checkout", "Stripe Checkout") | the PSP's own site. If the brand looks outdated (the PSP was acquired, renamed or folded into another product), keep the current name and flag it for the user with what you found and where |
| `websiteUrl()` | The PSP's developer documentation for this product, or its homepage, as `League\Uri\Uri::new('https://...')` | open it; it must answer over https without redirecting to an unrelated page |
| `logo()` | `Logo\Path::create(__DIR__ . '/Resources/logo.svg')` for a file in the package; `Logo\Url::create(...)` for the PSP's official asset URL | see below |

Research these on the web when you can. The 1.x `payum.factory_title`, README and `composer.json`
`homepage` are a starting point, not the answer: they are often years old. Say in the summary what you
checked and where.

Do not rebrand a gateway yourself. A new name changes what every application shows its merchants, so it
is the user's decision: report it as an open decision. A website URL that is dead or now redirects to
another product's page may be updated to the PSP's current page for the same product; say so in the
summary.

**The logo.** Prefer shipping an SVG in `Resources/` with `Logo\Path`, so it works offline and does not
break when the PSP moves its site. Take it only from the PSP's brand or press page, and check that the
PSP's brand terms allow redistribution. Do not download or commit a logo without telling the user where it
came from; if the terms are unclear, use `Logo\Url` pointing at the PSP's official asset and ask the user
to confirm. A `Logo\Url` must point at the image file itself (`.svg` or `.png`, answering with an
`image/*` content type), never at a press-kit or brand page; if you cannot find one, say so and leave the
decision to the user. Never draw or approximate a logo.

**Describing the package.** Update the package's `composer.json` `description`, `keywords` and `homepage`
and the README to match the 2.x gateway, with a registration example using `registerGateway()` and the
config class.
