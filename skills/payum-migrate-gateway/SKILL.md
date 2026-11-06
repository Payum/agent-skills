---
name: payum-migrate-gateway
description: Migrates a Payum 1.x gateway package (a GatewayFactory with payum.action.* actions, Action/Api request actions, a status action, extensions, an options-array Api) to the Payum 2.x structure of a gateway class, a typed config, handlers that return results, middleware and an autowired API, without breaking backward compatibility unless the user allows it. Use it to assess what a gateway needs, port the whole gateway, or port one action, API class or extension at a time; and whenever someone asks to upgrade, modernise, port or convert a Payum gateway, payment gateway package or PSP integration to 2.x/v2, replace actions with handlers or extensions with middleware, or declare a gateway's capabilities. Do not use it to upgrade an application that only uses Payum, or to build a new gateway from scratch with no 1.x code.
license: MIT
compatibility: Payum 2.x (payum/core 2.0+), PHP 8.1+, Composer. Works on any 1.x gateway package, not only the ones in the Payum repository.
---

# Migrate a Payum gateway from 1.x to 2.x

Port a 1.x gateway package to the 2.x model: a gateway class that describes itself, a config class that
validates itself, one handler per command that returns a result, middleware instead of extensions, and an
API class that takes its config through the constructor. Keep every feature the 1.x gateway has, and keep
every application that uses it working unless the user said a BC break is fine.

The work has three phases: **assess** (find everything, decide what each piece becomes), **port** (the
whole gateway or the pieces the user asked for), and **verify**. Always assess first, even for a single
action: a capture action you port alone still depends on the status action, the convert action and the
API requests it executes.

## 1. Establish the facts

Do these before reading any gateway code. Each one changes what you write.

1. **Find the package.** Locate the gateway's `composer.json`, its PSR-4 namespace and its source
   directory. A gateway inside a monorepo has its own `composer.json` under its directory.
2. **Read the PHP floor.** Take the lowest PHP version from `require.php` in the gateway's
   `composer.json` (the root one in a monorepo when the package has none). Payum 2.x needs 8.1, so the
   floor is at least 8.1 after migration. Raising it further is a BC break for the gateway's users: do it
   only if the user agrees. Use every language feature the floor allows and nothing newer (see
   [PHP versions](#php-versions)).
3. **Check which Payum is installed.** Run `composer show payum/core` in the project the gateway is
   developed in. You need 2.x installed to write and test 2.x code. If it shows 1.x, stop and tell the
   user to require `payum/core:^2.0` (or the 2.x dev branch) first. Treat the installed
   `vendor/payum/core/` source as the authority on class names and signatures: when the docs and the code
   disagree, the code is what runs.
4. **Fetch the current migration guide.** Payum publishes its docs as Markdown. Fetch
   `https://payum.dev/docs/v2/upgrading/migrating-from-v1.md` and read it fully; it changes as 2.x
   moves. Fetch the pages it links to (append `.md` to any docs URL; the index is
   `https://payum.dev/docs/llms.txt`) when you reach the matching step: handlers, results, commands,
   configuration, defining-a-gateway, services, templates, webhooks, middleware. If the network is
   unavailable, or the project has a `docs/` copy of these pages (the Payum repository itself does,
   under `docs/gateways/`), read those instead and say so in your summary.
5. **Find out how the package is released.** The version this change ships in goes into every
   deprecation message, `CHANGELOG` and `UPGRADE` heading, so work it out from the release process, not
   from the request alone:
   - Read the latest tag (`git tag --sort=-v:refname | head`), the `extra.branch-alias` in
     `composer.json`, and the top of the `CHANGELOG`.
   - Look for monorepo tooling: a root `composer.json` that `replace`s the package with `self.version`,
     split scripts (splitsh, `git subtree`, a `release` script) or a release workflow under
     `.github/workflows/`. In a monorepo that tags every package together, a package cannot release a
     version of its own.
   - If the version the user asked for does not fit the process (for example "release payum/offline 3.0"
     in a monorepo that tags everything 2.x), do not pick one silently. Write the version the process
     will actually produce, and flag the conflict as an open decision.
6. **Read the scope and the BC policy from the request.**
   - *Scope*: the whole gateway, or named pieces ("just the capture action", "the API class", "the
     extension"). If the user did not say and the gateway has more than about eight actions, finish the
     assessment, propose an order, and ask how far to go.
   - *BC*: preserve backward compatibility unless the user explicitly says breaking it is fine (for
     example "we are releasing a new major", "drop the factory"). Read
     [references/backward-compatibility.md](references/backward-compatibility.md) before porting anything
     in either mode.

## 2. Assess

1. **Inventory the package.** Run the bundled script against the gateway's source directory:

   ```bash
   python3 <skill-dir>/scripts/inventory.py <gateway-src-dir>
   ```

   It lists the factories and their config keys, every action with the requests it supports, the replies
   it throws and the sub-requests it executes, status marks, extensions, custom request classes, API
   classes, the keys stored in payment details, and templates. It is pattern based: read every file it
   lists, and every file it does not list, before you trust it.
2. **Read the tests.** The existing tests describe the behaviour you must keep. Note which ones exercise
   public API that applications use.
3. **Map every piece.** For each item in the inventory decide its 2.x target, using
   [references/conversion-recipes.md](references/conversion-recipes.md). Nothing may be left without a
   target: an item is ported, kept for BC with a deprecation, folded into another piece, or deleted with a
   reason.
4. **Work out the capabilities and metadata** with
   [references/capabilities-and-metadata.md](references/capabilities-and-metadata.md). Every declared
   capability needs evidence in the code or the PSP's documentation.
5. **List the gaps.** Call out anything 2.x has no direct equivalent for, such as several actions answering
   the same operation, `ObtainCreditCard`, custom requests applications execute directly, or replies core
   does not know. Propose a resolution for each.
6. **Present the assessment** to the user before writing code, in this shape:

   ```markdown
   ## Assessment: <package> (<n> actions, <n> API classes, <n> extensions)
   PHP floor: 8.x. Payum installed: 2.x. BC: preserved | breaking allowed.

   | 1.x piece | 2.x target | Notes / BC impact |
   | --- | --- | --- |
   | AcmeGatewayFactory | AcmeGateway + AcmeConfig; factory kept, deprecated | options map to config args |
   | Action/CaptureAction | Handler/CaptureHandler | throws HttpRedirect -> Redirect next action |
   | Action/StatusAction | status mapping in handlers; kept in actions() for 1.x-created payments | |

   Capabilities: derived (Capture, Refund, Webhooks) + declared (PartialRefund: RefundAction sends `amount`)
   Metadata: name, website, logo, with sources
   Gaps and decisions needed: ...
   Proposed order: config -> API -> gateway -> capture -> ...
   ```

   When the user asked for a full migration and nothing in the assessment needs their decision, continue
   straight to porting. When migrating one piece at a time, offer to save the assessment to a file in the
   package (for example `MIGRATION-2.x.md`), so the next session can pick up where this one stopped.

## 3. Port

### The whole gateway

Port in this order. Each step leaves the package working, so stop and run the tests after each one.

1. **Config class** from `payum.default_options` and `payum.required_options`: one `readonly`
   constructor argument per option, required options without defaults, validation in the constructor.
2. **API class**: take the config, a PSR-18 client and PSR-17 factories through the constructor. Turn
   every `Action/Api/*Action` into a method on it.
3. **Gateway class**: metadata, `configClass()`, `handlers()`, and `DeclaresCapabilities`,
   `DeclaresTemplates`, `DeclaresMiddleware` or `ContainerConfiguration` as needed.
4. **Handlers**, capture (or authorize) first, then refund, cancel, sync, payout. Fold the status
   action's mapping into the results the handlers return, and the convert action into the handlers that
   read the payment.
5. **Notify handler**: split the signature check into `verify()` and the rest into `handle()`.
6. **Templates and middleware**: `payum.paths` and `payum.template.*` to `DeclaresTemplates`,
   `payum.extension.*` to middleware.
7. **The BC layer** (skip only when a break is allowed): keep the factory and the public 1.x classes
   working, as [references/backward-compatibility.md](references/backward-compatibility.md) describes.
   Decide per operation whether the factory routes to the handler or keeps its action; the reference has
   the rule.
8. **Package metadata**: `composer.json` constraints, `CHANGELOG`, an upgrade note for the gateway's
   users, and the README's registration example switched to `registerGateway()` with the config class.

### One piece at a time

Port only what the user named, and bridge it so the gateway keeps working with a mix of 1.x and 2.x
parts. Pick the bridge by what the package already has:

| The package has | Port one operation by |
| :--- | :--- |
| Only the 1.x factory | Writing the handler, then registering it in the factory as `new HandlerToActionAdapter($handler)` under the same `payum.action.*` key. Skip the adapter and keep the action, delegating to the shared code, when the action executes sub-requests applications override or watch (see [references/backward-compatibility.md](references/backward-compatibility.md#preserving-bc)) |
| A 2.x gateway class | Adding the handler to `handlers()` and removing the action from `DeclaresActions::actions()` |
| A 2.x gateway class, action not yet ported, but callers send commands | Listing `Payum\Core\Legacy\Handler\<Op>ActionHandler` in `handlers()` and keeping the action in `actions()` |

A single API class or extension ports the same way: write the 2.x class, then make the 1.x action or the
factory use it, so there is one implementation. Read "Move one operation at a time" in the migration
guide for the rules: handlers are asked before actions, a status action wins over the recorded status,
and actions listed in `actions()` are built from the container, so they need their API through the
constructor, not `ApiAwareInterface`.

After each piece, update the saved assessment if there is one: what is done, what is next.

### Rules for every class you write

- `declare(strict_types=1);` and the package's existing code style. Run its fixer (`ecs`,
  `php-cs-fixer`) if it has one.
- Handlers and config classes are `final`, take services through the constructor, and keep no state
  between calls. Never take the payment, token or HTTP request in a constructor: they come on the
  `Context`.
- Read the amount with `$context->amount()`, never `$command->amount`, which is null on a full capture.
- Keep the payment details keys the 1.x gateway wrote (`$context->state()` is the same details array).
  Payments started before the upgrade come back to the new handlers with the old keys.
- Return a declined payment as `failed()` with a `Failure` and a mapped `FailureReason`. Let faults
  (network, bad credentials, malformed responses) throw.
- Never put a PSP's own status string in a result's status. Map it to a `PaymentStatus` case and keep the
  original in `raw`.
- Keep `SensitiveValue` wrapping in the state. Call `toUnsafeArray()` only to build the request sent to
  the PSP.
- Never put real credentials in code, tests or docs. Use sandbox placeholders.
- Write tests for every handler you add, mirroring the package's existing test layout. Port the 1.x
  action's test cases: same inputs, same PSP calls, the result in place of the reply.

## 4. Verify

1. Run the package's test suite. Every 1.x test must still pass in BC mode.
2. Run its static analysis (PHPStan, Psalm) if it has one. New code adds no baseline entries.
3. Run the conformance check from the gateway's project root:

   ```bash
   php <skill-dir>/scripts/check_gateway.php vendor/autoload.php 'Acme\Payum\AcmeGateway' \
     --config='{"apiKey":"sk_test_placeholder","sandbox":true}'
   ```

   It checks the no-argument constructor, metadata, the config and gateway naming each other, the handler
   map, that declared capabilities do not repeat derived ones, templates, middleware, and that
   `registerGateway()` and `getPayum()` build the gateway. The JSON holds the config's constructor
   arguments; use placeholders.
4. In BC mode, prove the 1.x path still works: the factory still builds a gateway, a 1.x `Capture`
   request still gets the reply it used to, and an existing details array still maps to the same status.
   A test that does this belongs in the package.

## PHP versions

Use what the floor allows, so the ported code reads like current PHP:

| Floor | Use |
| :--- | :--- |
| 8.1 | constructor promotion, `readonly` properties, enums, `never`, `new` in initialisers, first-class callables, pure intersection types, `array_is_list()` |
| 8.2 | `readonly` classes, standalone `null`/`true`/`false` types, DNF types |
| 8.3 | typed class constants, `#[\Override]`, `json_validate()` |
| 8.4 | property hooks, asymmetric visibility, `new` without parentheses in chains, `array_find()` |

Do not use a feature above the floor, even if the installed PHP has it.

## Before you say it is done

- [ ] Every item in the inventory has a 2.x target, a BC shim, or a recorded reason for deletion.
- [ ] Every operation the 1.x gateway supported still works, through a handler or a bridged action.
- [ ] Results carry the statuses the 1.x status action produced for the same details.
- [ ] Capabilities: derived ones come from handlers, declared ones each have evidence.
- [ ] Metadata is current: name, website and logo checked against the PSP's site. An outdated brand is
      flagged, not renamed.
- [ ] Deprecation versions and `CHANGELOG`/`UPGRADE` headings match the version the release process will
      produce; any conflict with what the user asked for is flagged.
- [ ] No deprecated 2.x API in new code: no `ApiAwareInterface`, `payum.api.*`, `HttpClientInterface`,
      `php-http/message-factory`, `GatewayAwareTrait` in handlers.
- [ ] BC mode: the factory, option keys, public classes and stored details keys still work, with
      deprecations pointing at their replacements. Breaking mode: every break is listed in the upgrade
      note.
- [ ] No language feature above the PHP floor.
- [ ] Tests, static analysis and `check_gateway.php` pass. Say which ones you ran and what failed.
- [ ] The summary names what was ported, what was kept for BC, what is left, and any decision the user
      still has to make.
