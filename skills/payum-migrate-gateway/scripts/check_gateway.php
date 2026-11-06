<?php

declare(strict_types=1);

/*
 * Checks a Payum 2.x gateway class against the rules Payum enforces at runtime, and the ones it cannot.
 *
 * Usage:
 *   php check_gateway.php <autoload.php> <Gateway\Class> [--config='{"apiKey":"sk_test"}']
 *
 * With --config, the JSON object is passed as named arguments to the config class's constructor, and the
 * gateway is registered on a PayumBuilder and built, which is what an application does. Use sandbox or
 * placeholder values only: nothing is sent to the PSP. The script reads the gateway and writes nothing.
 * Exit code 0 when every check passes, 1 otherwise.
 */

if ($argc < 3 || in_array('--help', $argv, true)) {
    fwrite(STDERR, "Usage: php check_gateway.php <autoload.php> <Gateway\\Class> [--config='<json>']\n");
    exit(in_array('--help', $argv, true) ? 0 : 2);
}

require $argv[1];

use Payum\Core\Config\GatewayConfig;
use Payum\Core\Gateway\Capability;
use Payum\Core\Gateway\DeclaresActions;
use Payum\Core\Gateway\DeclaresCapabilities;
use Payum\Core\Gateway\DeclaresMiddleware;
use Payum\Core\Gateway\DeclaresTemplates;
use Payum\Core\Gateway\GatewayInterface;
use Payum\Core\Handler\HandlerMap;
use Payum\Core\Metadata\Logo;
use Payum\Core\Middleware\MiddlewareInterface;
use Payum\Core\PayumBuilder;

$gatewayClass = $argv[2];
$configJson = null;
foreach (array_slice($argv, 3) as $arg) {
    if (str_starts_with($arg, '--config=')) {
        $configJson = substr($arg, 9);
    }
}

$failures = 0;
$check = static function (bool $ok, string $message) use (&$failures): void {
    echo($ok ? '  ok    ' : '  FAIL  ') . $message . "\n";
    $failures += $ok ? 0 : 1;
};
$note = static fn (string $message) => print '  note  ' . $message . "\n";

echo "Gateway {$gatewayClass}\n";

if (! class_exists($gatewayClass) || ! is_a($gatewayClass, GatewayInterface::class, true)) {
    $check(false, 'class exists and implements ' . GatewayInterface::class);
    exit(1);
}

$constructor = (new ReflectionClass($gatewayClass))->getConstructor();
$check(null === $constructor || 0 === $constructor->getNumberOfRequiredParameters(), 'constructs with no arguments');
$gateway = new $gatewayClass();

$check('' !== trim($gateway->name()), sprintf('name() is "%s"', $gateway->name()));

$logo = $gateway->logo();
$check($logo instanceof Logo, 'logo() returns a ' . Logo::class);
if ($logo instanceof Logo\Path) {
    $check(is_file($logo->getValue()), 'logo file exists: ' . $logo->getValue());
} else {
    $note(sprintf('logo is a %s (%s); prefer Logo\Path to a file shipped in the package', $logo::class, substr($logo->getValue(), 0, 80)));
}

$url = (string) $gateway->websiteUrl();
$check(str_starts_with($url, 'https://'), 'websiteUrl() is https: ' . $url);

$configClass = $gateway->configClass();
$check(is_a($configClass, GatewayConfig::class, true), "configClass() {$configClass} implements " . GatewayConfig::class);
if (is_a($configClass, GatewayConfig::class, true)) {
    $config = (new ReflectionClass($configClass))->newInstanceWithoutConstructor();
    try {
        $check($config->getGatewayClass() === $gatewayClass, 'the config\'s getGatewayClass() names this gateway');
    } catch (Throwable $e) {
        $note('could not call getGatewayClass() without constructing the config: ' . $e->getMessage());
    }
    foreach ((new ReflectionClass($configClass))->getProperties(ReflectionProperty::IS_PUBLIC) as $property) {
        if (! $property->isReadOnly() && ! $property->isStatic()) {
            $check(false, "config property \${$property->getName()} is readonly");
        }
    }
}

$capabilities = [];
try {
    $map = HandlerMap::fromHandlers($gateway->handlers());
    $capabilities = $map->capabilities();
    $check(true, sprintf('handlers() maps %d handler(s): %s', count($gateway->handlers()), implode(', ', array_map(static fn ($c) => basename(str_replace('\\', '/', $c)), $map->commands()))));
} catch (Throwable $e) {
    $check(false, 'handlers() is valid: ' . $e->getMessage());
}

if ($gateway instanceof DeclaresCapabilities) {
    $declared = $gateway->capabilities();
    $overlap = array_filter($declared, static fn (Capability $c) => in_array($c, $capabilities, true));
    $check([] === $overlap, 'capabilities() repeats none that handlers imply' . ([] === $overlap ? '' : ': ' . implode(', ', array_map(static fn ($c) => $c->name, $overlap))));
    $capabilities = array_values(array_unique([...$capabilities, ...$declared], SORT_REGULAR));
}
$note('capabilities: ' . (implode(', ', array_map(static fn (Capability $c) => $c->name, $capabilities)) ?: 'none'));

if ($gateway instanceof DeclaresTemplates) {
    foreach ($gateway->templateNamespaces() as $namespace => $dir) {
        $check('PayumCore' !== $namespace, "template namespace {$namespace} is not PayumCore");
        $check(is_dir($dir), "template directory exists: {$dir}");
    }
}

if ($gateway instanceof DeclaresMiddleware) {
    foreach ($gateway->middleware() as $middleware) {
        $check(is_string($middleware) && is_a($middleware, MiddlewareInterface::class, true), "middleware {$middleware} implements " . MiddlewareInterface::class);
    }
}

if ($gateway instanceof DeclaresActions) {
    $note('still declares 1.x actions: ' . implode(', ', $gateway->actions()) . '. Fine mid-migration; remove when every action is a handler.');
}

if (null !== $configJson) {
    try {
        $config = new $configClass(...json_decode($configJson, true, 512, JSON_THROW_ON_ERROR));
        $payum = (new PayumBuilder())
            ->addDefaultStorages()
            ->registerGateway('check', $config)
            ->getPayum();
        $payum->getGateway('check');
        $check(true, 'registerGateway() and getPayum() build the gateway');
    } catch (Throwable $e) {
        $check(false, 'registerGateway() and getPayum() build the gateway: ' . $e::class . ': ' . $e->getMessage());
    }
}

echo 0 === $failures ? "All checks passed.\n" : "{$failures} check(s) failed.\n";
exit(0 === $failures ? 0 : 1);
