# Backward compatibility while migrating

A gateway package has users who upgrade on their own schedule. Unless the user said a BC break is fine,
every application that worked with the 1.x package must keep working, with deprecation notices telling it
what to change. Read the section for the mode you are in.

## Contents

- [The public surface](#the-public-surface)
- [Preserving BC](#preserving-bc)
- [Payments already in flight](#payments-already-in-flight)
- [Composer constraints](#composer-constraints)
- [Deprecation messages](#deprecation-messages)
- [When a BC break is allowed](#when-a-bc-break-is-allowed)
- [What to tell the gateway's users](#what-to-tell-the-gateways-users)

## The public surface

List these from the inventory and the README before porting. Each one is something an application may
depend on:

| Surface | How applications use it |
| :--- | :--- |
| The factory class and its `payum.factory_name` | `addGatewayFactory('acme', new AcmeGatewayFactory())`, `addGateway('acme', ['factory' => 'acme', ...])`, Symfony/Laravel bundle config |
| Option keys and their defaults | config arrays, and gateway configs stored in a database (`GatewayConfigInterface::getConfig()`), so renaming one silently breaks stored rows |
| `payum.action.*`, `payum.extension.*`, `payum.template.*` keys | applications replace or remove them (`'payum.action.capture' => new MyCaptureAction()`, `'payum.extension.x' => null`) |
| Action, extension and API classes | extended, decorated, or constructed by hand; the API's constructor signature and public methods |
| Custom request classes (`Request/Api/*`, `ObtainToken`, `CreatePlan`) | executed directly by applications: `$gateway->execute(new CreatePlan($details))` |
| Constants classes | status strings and field names applications compare against |
| Keys and values in payment details | read by applications (`$payment->getDetails()['transaction_id']`) and by the gateway itself on the customer's return |
| Template names | applications override `@PayumAcme/...` templates |
| Replies a 1.x caller catches | `HttpRedirect`, `HttpResponse`, custom replies |

## Preserving BC

The aim is one implementation of each operation, the 2.x one, with the 1.x surface delegating to it.

**The factory stays and builds the same gateway.** Keep `AcmeGatewayFactory` and its
`payum.factory_name`, `payum.factory_title`, option keys and defaults, and deprecate the class (see
[Deprecation messages](#deprecation-messages)). Keep the factory's validation behaviour: an option that
was optional in 1.x must not become required in the factory.

Then choose how each operation runs on the factory's gateway. Aim for one implementation either way:

| Choose | When | How |
| :--- | :--- | :--- |
| Route the operation to the handler | Nothing outside the action depends on how it runs: the action executes no sub-request an application overrides or watches | Register the handler under the action's old key through `Payum\Core\Legacy\HandlerToActionAdapter` |
| Keep the 1.x action, delegating | The action executes `Convert`, an `Action/Api` request or another sub-request that applications can replace (`payum.action.convert_payment`, `payum.action.api.*`) or observe with an extension | Leave the action registered, and move its logic into the API class and a shared mapper the handler uses too |

The adapter runs the handler instead of the action, so the sub-requests the action used to execute never
happen. An application that overrode `payum.action.convert_payment` to add fields, or an extension that
reacts to `CreateTransaction`, then stops working without an error. Look for those hooks in the README,
the docs and the tests before you route an operation to the handler. When in doubt, keep the action and
say why in the summary.

When you route to the handler, build its dependencies from the options inside the closure, so they exist
once the application's options are merged in. 1.x closures are resolved in key order, so do not rely on
`$config['payum.api']` being built yet:

```php
use Http\Discovery\Psr17FactoryDiscovery;
use Http\Discovery\Psr18ClientDiscovery;
use Payum\Core\Legacy\HandlerToActionAdapter;

protected function populateConfig(ArrayObject $config): void
{
    $config->defaults([
        'payum.factory_name' => 'acme',
        'payum.factory_title' => 'Acme',
        'payum.action.capture' => static fn (ArrayObject $config) => new HandlerToActionAdapter(
            new CaptureHandler(self::api($config)),
        ),
        // ...
    ]);
    // payum.default_options, payum.required_options and payum.api as before
}

private static function api(ArrayObject $config): AcmeApi
{
    $config->validateNotEmpty($config['payum.required_options']);

    return new AcmeApi(
        new AcmeConfig(apiKey: $config['api_key'], sandbox: (bool) $config['sandbox']),
        Psr18ClientDiscovery::find(),
        Psr17FactoryDiscovery::findRequestFactory(),
        Psr17FactoryDiscovery::findStreamFactory(),
    );
}
```

`HandlerToActionAdapter` only claims a request whose model is a payment or payout. A request carrying a
bare details array still needs the 1.x action, so when you route an operation to the handler, keep the
old action registered under a new key (for example `payum.action.capture_details`) and list that key in
the upgrade note: an application that set the old key to `null` to turn the operation off now has to
null both.

Check the factory's gateway with a test either way: `(new AcmeGatewayFactory())->create([...options])`,
execute a 1.x `Capture` on a payment and on a details array, and assert the reply and the status a
`GetHumanStatus` reports.

**Option keys stay the option keys.** The config class's argument names are new (`apiKey`), but the
factory still reads `api_key`. If the config has a named constructor for the old shape, such as
`AcmeConfig::fromOptions(array $options)`, the factory and applications moving off arrays can share it.

**Public classes stay, deprecated.** Keep action, extension, request and constants classes that
applications might reference. An action you ported becomes a thin class that delegates to the handler or
the API, or stays unchanged if rewriting it buys nothing; either way it gets a deprecation. Keep the API
class's old constructor working when applications construct it: accept the old options array as well
(`AcmeConfig|array $config`, converting the array and triggering a deprecation), or keep the old class and
add the new one beside it. Keep every public API method an application might call, with its signature.

**Custom requests applications execute.** A 2.x gateway class answers 1.x requests only through
`DeclaresActions::actions()`. If applications execute `new CreatePlan(...)` against the gateway, keep
the request class and its action, make the action call the new API method, and list it in `actions()`
on the gateway class too, so an application that moves to `registerGateway()` keeps the request working.
Deprecate both and name the API method as the replacement.

**Templates keep their names.** Keep the `@PayumAcme/...` names and the files, so overrides still apply.
Declare the same namespace in `DeclaresTemplates::templateNamespaces()`. Keep the `payum.template.*`
keys in the factory.

**Extensions keep running on the factory.** Port the extension to a middleware for the gateway class,
and keep the extension registered in the factory (or make it delegate) until 3.0, because a factory-built
gateway does not run gateway middleware.

## Payments already in flight

A customer can leave for the PSP before the upgrade and come back after it. The new handler then sees a
details array the 1.x code wrote.

- Keep every details key and its meaning. Add new keys rather than renaming old ones.
- Keep the second-run detection the 1.x action used (for example "`checkout_id` is set"), so a returning
  customer is not sent to the PSP again.
- **Keep the status action while 1.x payments exist.** A 1.x status request on a ported gateway is
  answered from the status Payum recorded on the payment. A payment created before the upgrade has no
  recorded status, so it reads as unknown. List the status action in `DeclaresActions::actions()` on the
  gateway class (a status action wins over the recorded status) and keep it in the factory. Remove it
  in the gateway's next major. The handlers must produce the same statuses it does for the same details.
- A test that feeds a details array written by the 1.x code into the new handler proves this.

## Composer constraints

- Requiring `payum/core: ^2.0` drops Payum 1.x users. That is expected for this migration, but it is a
  breaking change for the package: release it as the package's next major version, or as a minor only if
  the package already requires Payum 2.x. Check the release process first (step 1 of `SKILL.md`): in a
  monorepo that tags every package together, the version is not the package's to choose.
- Keep the PHP floor unless the user agrees to raise it. Payum 2.x needs PHP 8.1.
- Add a dependency only for code you wrote that needs it, for example `league/uri` (already required by
  `payum/core`) or `psr/clock`. Remove `php-http/message-factory`; Payum no longer installs it.
- In a monorepo, change both the package's `composer.json` and the root one.

## Deprecation messages

Use `trigger_deprecation()` from `symfony/deprecation-contracts`, which `payum/core` requires. Name the
package, the version that deprecates it and the replacement, and say when it goes:

```php
trigger_deprecation(
    'acme/payum-acme',
    '3.0.0',
    '%s is deprecated and will be removed in 4.0. Register %s with PayumBuilder::registerGateway() instead.',
    AcmeGatewayFactory::class,
    AcmeConfig::class,
);
```

Trigger it where the old path is used (a constructor, `populateConfig()`), not at file load. Add an
`@deprecated` tag with the same replacement to the class docblock, so IDEs and static analysis see it.

## When a BC break is allowed

When the user releases a new major and allows breaks:

- Delete the factory, the actions, the status and convert actions, the `Action/Api` actions and the
  custom requests once nothing in the package uses them.
- Rename option keys freely in the config class, but list each rename.
- The API class may take the config only.
- Stored details keys still matter: payments in flight and stored gateway configs do not care about the
  version number. Keep the keys, or write a migration note telling users how to convert stored rows.
- List every removed class, renamed option and changed signature in the upgrade note.

## What to tell the gateway's users

Write an upgrade note (the package's `UPGRADE.md` or a section of its README/CHANGELOG):

- How to register the gateway now, with the old and new registration side by side.
- The option to config argument mapping.
- What is deprecated, what replaces it, and when it goes.
- That a custom `Convert` action, or other `payum.action.*` entries an application added, are ignored by
  the 2.x gateway class (Payum raises a deprecation naming each), and where that data goes instead: onto
  the payment's details before the command runs.
- Any new requirement: a payment model implementing `Payum\Core\Model\StatusAwareInterface` for status,
  a PSR-18 client, a `ServerRequestInterface` registered with `addGlobalService()` when the notify
  handler reads the request body behind a framework or worker server.
- In breaking mode, every break.
