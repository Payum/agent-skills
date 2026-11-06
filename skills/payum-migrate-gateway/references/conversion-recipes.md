# Conversion recipes

What each kind of 1.x piece becomes. The migration guide
(`https://payum.dev/docs/v2/upgrading/migrating-from-v1.md`) has the basic map and a worked example;
this file covers the cases it does not spell out. Check every class and method name here against
`vendor/payum/core/` before you use it.

## Contents

- [Factory and options](#factory-and-options)
- [API classes and Action/Api actions](#api-classes-and-actionapi-actions)
- [Operation actions](#operation-actions)
- [Several actions for one operation](#several-actions-for-one-operation)
- [Status action](#status-action)
- [Convert action](#convert-action)
- [Sub-requests](#sub-requests)
- [Replies](#replies)
- [Declines and errors](#declines-and-errors)
- [Notify action](#notify-action)
- [Credit cards](#credit-cards)
- [Extensions](#extensions)
- [Templates](#templates)
- [Services the API cannot autowire](#services-the-api-cannot-autowire)

## Factory and options

| 1.x | 2.x |
| :--- | :--- |
| `payum.default_options` entry `'sandbox' => true` | `public readonly bool $sandbox = true` on the config |
| `payum.required_options` entry `'api_key'` | `public readonly string $apiKey` with no default, and a check in the constructor that throws `Payum\Core\Exception\InvalidArgumentException` when it is empty |
| `payum.factory_title` | `GatewayInterface::name()` |
| `payum.factory_name` | nothing: the application names the gateway in `registerGateway()` |
| `payum.action.*` | `handlers()`, one class per command |
| `payum.extension.*` | `DeclaresMiddleware::middleware()` |
| `payum.paths`, `payum.template.*` | `DeclaresTemplates::templateNamespaces()`; template names move into the handlers |
| `payum.api` closure | the API class, autowired, or a `ContainerConfiguration` definition |
| Options that are URLs per environment | a method on the config, such as `baseUrl()`, deciding from `sandbox` |
| An option holding a choice from a fixed list | a string-backed enum (PHP 8.1), with the old string accepted by the factory |

Keep option semantics: a 1.x option that accepted `'1'` or `true` should not throw for `'1'` in the
factory path. Type the config strictly and convert in the factory.

A factory that registers several gateways (Stripe Checkout, Stripe Js and Stripe Direct share actions)
becomes several gateway classes, each with its own config, sharing handlers and the API class where the
behaviour is the same.

## API classes and Action/Api actions

- Change the constructor to take the config class, `Psr\Http\Client\ClientInterface` and the PSR-17
  `RequestFactoryInterface` / `StreamFactoryInterface`. Replace `Payum\Core\HttpClientInterface`,
  `Http\Message\MessageFactory` and `HttpClient` calls with PSR-18 `sendRequest()`.
- Each `Action/Api/FooAction` answering `new Foo($details)` becomes `$api->foo(...)`. Move the action's
  logic into the API method, but give the method typed parameters for what it needs rather than the whole
  details array when that is clearer. The handler writes the response into the state.
- An action that executed `GetHttpRequest`, `RenderTemplate` or another sub-request cannot become an API
  method as is: the API never sees the HTTP request or renders anything. Move that part into the
  handler and keep only the PSP call in the API.
- An SDK that is configured statically (`Stripe::setApiKey()`) keeps that call inside the API method that
  uses the SDK, so two registered gateways with different keys do not overwrite each other between calls.
- A SOAP or SDK client built from options becomes a `ContainerConfiguration` definition, or is built
  lazily inside the API class from the config.

## Operation actions

| 1.x action supports | Handler interface | Result |
| :--- | :--- | :--- |
| `Capture` | `CaptureHandlerInterface` | `CaptureResult` |
| `Authorize` | `AuthorizeHandlerInterface` | `AuthorizeResult` |
| `Refund` | `RefundHandlerInterface` | `RefundResult` |
| `Cancel` | `CancelHandlerInterface` | `CancelResult` |
| `Sync` | `SyncHandlerInterface` | `SyncResult` |
| `Payout` | `PayoutHandlerInterface` | `PayoutResult` |
| `Notify` | `NotifyHandlerInterface` | `NotifyResult` |

For each action:

1. Drop `supports()` and `assertSupports()`. Note what `supports()` checked beyond the request class (a
   details key, a model type): that condition decides whether this handler or another code path runs.
2. Replace `ArrayObject::ensureArrayObject($request->getModel())` with `$context->state()`.
3. Replace `$request->getToken()` with `$context->token()`, `$request->getFirstModel()` with
   `$context->payment()` or `$context->payout()`.
4. Replace each sub-request (below) and each thrown reply (below).
5. Return a result on every path. A path that returned nothing in 1.x returns `pending()` (still waiting)
   or the status the status action would have reported for that state.
6. Replace `$this->gateway->execute(new Sync($details))` inside an operation with a private method or an
   API call; dispatch `$context->execute(SyncCommand::forPayment($payment))` only when you need the full
   sync result.
7. Abstract base actions (`PurchaseAction`, `BaseApiAwareAction`) become private methods on the handler
   or a small shared service the handlers take in their constructor.

A capture that redirects runs twice, and the handler tells the runs apart from its state. Keep the 1.x
action's way of telling them apart.

## Several actions for one operation

2.x allows one handler per command. When the inventory shows two actions answering the same request
(PayPal's `CancelAction` and `CancelRecurringPaymentsProfileAction`, two sync actions for payments and
recurring profiles), write one handler that branches on the same condition the actions' `supports()`
methods used, usually the shape of the details. Keep each branch in its own private method or service so
the handler stays readable. If the branches are really separate products, propose a separate gateway
class for one of them and ask the user, because that changes how applications register it.

## Status action

The status action disappears into the results. Turn its `markX()` calls into the statuses the handlers
return:

| `markX()` | `PaymentStatus` | Typical result |
| :--- | :--- | :--- |
| `markNew()` | `New` | `pending()` before anything was sent, or no status change |
| `markPending()` | `Pending` | `CaptureResult::pending()` |
| `markAuthorized()` | `Authorized` | `AuthorizeResult::authorized($id, ...)` |
| `markCaptured()` | `Captured` / `PartiallyCaptured` | `CaptureResult::captured($id)`, `partiallyCaptured($id, $amount)` |
| `markRefunded()` | `Refunded` / `PartiallyRefunded` | `RefundResult::refunded(...)`, `partiallyRefunded(...)` |
| `markCanceled()` | `Canceled` | `CancelResult::canceled($id)`, `CaptureResult::canceled()` |
| `markFailed()` | `Failed` | `failed($failure, PaymentStatus::Failed)` when final |
| `markExpired()` | `Expired` | `SyncResult::synced(PaymentStatus::Expired)` |
| `markSuspended()` | `Suspended` | `SyncResult::synced(PaymentStatus::Suspended)` |
| `markPayedout()` | `PaidOut` | `PayoutResult::paidOut($id, ...)` |
| `markUnknown()` | `Unknown` | `SyncResult::synced(PaymentStatus::Unknown)` |

Move the status action's decision logic into one private method or a small mapper class that takes the
state and returns a `PaymentStatus`, and use it from the capture, sync and notify handlers, so they agree.
Write a test that runs each details fixture from the status action's tests through the mapper and
expects the same status. The result's named constructor decides more than the status: pick the one whose
meaning matches (`partiallyCaptured()` needs the amount; `failed()` leaves the status alone unless you
pass one).

In BC mode the status action stays listed for payments created before the upgrade; see
[backward-compatibility.md](backward-compatibility.md#payments-already-in-flight).

## Convert action

A convert action copied payment fields into the details. In 2.x the handler reads the payment directly:

| 1.x | 2.x |
| :--- | :--- |
| `$payment->getTotalAmount()` | `$context->amount()` (a `Money`, also right for partial operations) |
| `$payment->getCurrencyCode()` | `$context->amount()->getCurrency()->getCode()` |
| `GetCurrency` for the decimal places | `Money\MoneyFormatter` / `Money\Currencies` from the constructor, see the money docs page |
| `$payment->getNumber()`, `getDescription()`, `getClientEmail()`, `getClientId()` | the same getters on `$context->payment()` |
| `$details->defaults($payment->getDetails())` | `$context->state()` already is the payment's details |

Write the PSP fields into the state the first time the handler runs, under the same keys the convert
action used, so payments in flight and applications reading details see what they used to.

## Sub-requests

| The action executed | The handler uses |
| :--- | :--- |
| `GetHttpRequest` | `$context->httpRequest()`: `->query` is `getQueryParams()`, `->request` is `getParsedBody()` (`$_REQUEST` merged both; pick the one you mean), `->method` is `getMethod()`, `->content` is `(string) getBody()`, `->headers` is `getHeaders()`, `->clientIp` is `getServerParams()['REMOTE_ADDR']`, `->uri` is `(string) getUri()` |
| `GetToken($hash)` | `$context->token()` |
| `GetCurrency($code)` | `Money\Currencies` in the constructor |
| `RenderTemplate($name, $vars)` then `throw new HttpResponse(...)` | `return ...::pending(new RenderTemplate($name, $vars))` |
| `GenericTokenFactory::createNotifyToken()` | `$context->notifyUrl()` / `$context->notifyToken()` |
| `createAuthorizeToken()`, `createCaptureToken()`, ... | `$context->tokens()->create(TokenPurpose::Authorize, $context->gatewayName(), $context->subject(), $afterUrl)` |
| `Sync`, `Capture`, `Cancel` on the same gateway | `$context->execute(SyncCommand::forPayment($context->payment()))` and the others |
| An `Api` request (`new CreateCharge($details)`) | the API method |
| `ObtainCreditCard` | see [Credit cards](#credit-cards) |

## Replies

| Thrown in 1.x | Returned in 2.x |
| :--- | :--- |
| `HttpRedirect($url)` | `new Redirect($url)` |
| `HttpPostRedirect($url, $fields)` | `new PostRedirect($url, $fields)` |
| `HttpResponse($html)` of a rendered template | `new RenderTemplate($template, $vars)` |
| `HttpResponse` answering a webhook | an `Acknowledgement` on the `NotifyResult` |
| A 3-D Secure redirect or form | `new Challenge($url, $parameters, $version)` |
| A "come back later" page or loop | `new Poll($retryAfterSeconds)`, and document that `Payum::capture()` cannot act on it |
| A reply class of the gateway's own | the closest next action above; if none fits, keep throwing it from a bridged action and tell the user, because handlers cannot return it |

Next actions are in `Payum\Core\Result\NextAction`. Return them on `pending()` (or the operation's
equivalent) with `$result->next`.

## Declines and errors

- A PSP response that says "declined", "insufficient funds", "expired card", "fraud", "3DS failed" is a
  result: `failed(new Failure(FailureReason::X, code: $pspCode, message: $pspMessage))`. Map each PSP code
  the 1.x code knew about to a `FailureReason`. Leave the status null unless the payment is finished.
- A transport error, an authentication error or a malformed response is an exception. Keep or introduce a
  package exception extending a Payum exception; do not turn it into a failed result.
- Where the 1.x action stored an error in the details (`$details['error'] = ...`) and the status action
  marked failed, keep writing the key and return the failure.

## Notify action

1. Move signature, IP or shared-secret checks into `verify(ServerRequestInterface $request)`, which
   returns `WebhookEvent::verified($payload, $id, $type)` or throws `WebhookNotVerifiedException`. Read the
   signed body with `(string) $request->getBody()` and compare with `hash_equals()`.
2. A PSP that signs nothing returns `WebhookEvent::unverified(...)`; the handler then dispatches a
   `SyncCommand` instead of trusting the message, which needs a sync handler.
3. In `handle()`, compare the PSP's reference in the message with the one in the state before acting,
   and return `NotifyResult::ignored()` for unknown event types.
4. A 1.x notify action that executed `Sync` and threw `HttpResponse('OK')` becomes
   `NotifyResult::handled($synced->status, Acknowledgement::ok('OK'))`. Keep the exact body the PSP
   expects.
5. A PSP with one dashboard-configured webhook URL (no notify token): the handler finds the payment from
   the message, because `$context->payment()` is null for `NotifyCommand::forGateway()`. If the 1.x
   gateway relied on the application to find the payment, say so in the upgrade note.

## Credit cards

Core does not answer `ObtainCreditCard` for a handler, and there is no command for it. Choose with the
user:

- The PSP has hosted fields or a JavaScript tokeniser: return a `RenderTemplate` with the PSP's script,
  and read the token from `getParsedBody()` on the second run. This keeps card data off the server.
- The application collects the card: read it from the payment when the model implements
  `Payum\Core\Model\CreditCardPaymentInterface` (`$context->payment()->getCreditCard()`), and keep the
  values wrapped in `SensitiveValue` in the state.
- Keep the 1.x action that executes `ObtainCreditCard` in `actions()` until the gateway's next major,
  for applications whose framework bridge renders the card form.

## Extensions

| Extension hook | Middleware |
| :--- | :--- |
| `onPreExecute(Context $context)` | code before `$next($command, $context)` |
| `onExecute(Context $context)` | code before `$next`; there is no separate "action chosen" step |
| `onPostExecute(Context $context)` | code after `$next`, reading the `Result` |
| `$context->getReply()` / `setReply()` | read `$result->next`; return a different result to change it |
| `$context->getException()` | wrap `$next` in `try` / `catch` or `finally` |
| `$context->getRequest() instanceof Capture` | `$command instanceof CaptureCommand` |
| `$context->getPrevious()` | `$context->previous()` |

A middleware implements `Payum\Core\Middleware\MiddlewareInterface::process(CommandInterface $command,
Context $context, callable $next): Result`. List it in `DeclaresMiddleware::middleware()`; its constructor
is autowired. An extension that executed API requests (Stripe's `CreateCustomerExtension`) usually reads
better as a step in the handler or the API; propose that when the extension only serves one operation.
Work that only calls the PSP, such as fetching an access token, belongs in the API class, not middleware.

## Templates

- Declare the namespace the 1.x `payum.paths` used, for example
  `'PayumAcme' => __DIR__ . '/Resources/views'`. Never `PayumCore`.
- Templates that extended `payum.template.layout` extend `layout` and put markup in `payum_body`. Payum
  passes `layout`, `gateway`, `subject`, `token`, `command` and `context` to every template; drop
  variables the handler only passed to recreate these.
- Forms post to `{{ token.targetUrl }}`, which reruns the capture.

## Services the API cannot autowire

Implement `Payum\Core\DI\ContainerConfiguration` on the gateway class only for a constructor argument that
is a scalar, an array, or an interface with several implementations. Return PHP-DI definitions keyed by
class name. Do not define `Payum\Core\Template\RendererInterface`; Payum refuses it.
