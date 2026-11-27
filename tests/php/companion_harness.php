<?php
/** Controlled WordPress/wpdb API simulation. NOT real WordPress or MySQL. */
$scenario = $argv[1] ?? 'success';
define('ABSPATH', __DIR__);
define('ARRAY_A', 'ARRAY_A');
define('FILIP_GUARD_TEST_REPAIRS', $scenario !== 'disabled');
$GLOBALS['env'] = $scenario === 'production' ? 'production' : 'staging';
$GLOBALS['ssl'] = $scenario !== 'http';
$GLOBALS['can_edit'] = $scenario !== 'forbidden';
$GLOBALS['options'] = array();
$GLOBALS['actions'] = array();
$GLOBALS['fail_update_option'] = false;

class WP_Post {
    public $post_status;
    public function __construct($row) { $this->post_status = $row->post_status; }
}
function wp_transition_post_status($new, $old, $post) { $GLOBALS['save_hooks'][] = 'transition_post_status'; }
function do_action($hook, ...$args) { $GLOBALS['save_hooks'][] = $hook; }
function wp_after_insert_post($post, $update, $before) { $GLOBALS['save_hooks'][] = 'wp_after_insert_post'; }
class WP_Error {
    public function __construct(public $code, public $message, public $data) {}
}
class WP_REST_Response {
    public $headers = array();
    public function __construct(public $data, public $status) {}
    public function header($key, $value) { $this->headers[$key] = $value; }
}
class Request {
    public function __construct(public $data = null, public $kind = 'post', public $id = '10') {}
    public function get_url_params() { return array('kind' => $this->kind, 'id' => $this->id); }
    public function get_json_params() { return $this->data; }
    public function get_body() { return json_encode($this->data); }
}
function is_wp_error($value) { return $value instanceof WP_Error; }
function wp_get_environment_type() { return $GLOBALS['env']; }
function is_ssl() { return $GLOBALS['ssl']; }
function get_current_user_id() { return 7; }
function current_user_can($capability, $id = null) { return $GLOBALS['can_edit'] && $capability === 'edit_post' && $id === 10; }
function clean_post_cache($id) {}
function wp_json_encode($value) { return json_encode($value); }
function current_time($format, $gmt = false) { return '2026-11-23 20:00:00'; }
function wp_kses_post($content) { return preg_replace('#<script>.*?</script>#s', '', $content); }
function get_option($name, $default) { return $GLOBALS['options'][$name] ?? $default; }
function add_option($name, $value, $deprecated, $autoload) {
    if (isset($GLOBALS['options'][$name])) { return false; }
    if ($autoload !== false) { throw new Exception('Options must not autoload'); }
    $GLOBALS['options'][$name] = $value;
    return true;
}
function update_option($name, $value, $autoload) {
    if ($GLOBALS['fail_update_option']) { return false; }
    $GLOBALS['options'][$name] = $value;
    return true;
}
function add_action($hook, $callback, $priority = 10, $count = 1) { $GLOBALS['actions'][$hook] = $callback; }
function register_rest_route($namespace, $route, $endpoints) {
    check($namespace === 'filip-guard/v1', 'namespace');
    if ($route === '/ownership' || str_ends_with($route, '/compatibility')) { check(isset($endpoints['permission_callback']), 'ownership permissions'); return; }
    check(count($endpoints) === 2, 'GET and POST registered');
    foreach ($endpoints as $endpoint) { check(isset($endpoint['permission_callback']), 'permission callback'); }
}
function check($condition, $label) { if (!$condition) { throw new Exception('Assertion failed: ' . $label); } }
function code($response, $expected) {
    check($response instanceof WP_Error, 'expected error ' . $expected);
    check($response->code === $expected, 'error code ' . $expected . ' got ' . $response->code);
}
class FakeDB {
    public $posts = 'wp_posts';
    public $row;
    public $queries = 0;
    public $race = false;
    public $fail = false;
    public $change_after_write = false;
    public function __construct() {
        $this->row = array('ID' => '10', 'post_type' => 'post', 'post_status' => 'publish',
            'post_author' => '7', 'post_title' => 'Title', 'post_content' => '<p>Original</p>',
            'post_modified' => '2026-11-22 10:00:00', 'post_modified_gmt' => '2026-11-22 10:00:00');
    }
    public function prepare($sql, ...$args) {
        if (count($args) === 1 && is_array($args[0])) { $args = $args[0]; }
        check(substr_count($sql, '%s') + substr_count($sql, '%d') === count($args), 'prepared parameter count');
        return array($sql, $args);
    }
    public function get_row($prepared, $mode) { return $this->row; }
    public function query($prepared) {
        $this->queries++;
        if ($this->fail) { return false; }
        if ($this->race) { $this->row['post_title'] = 'Concurrent title'; $this->race = false; }
        list($sql, $values) = $prepared;
        check(str_starts_with($sql, 'UPDATE wp_posts SET post_content = %s, post_modified = %s, post_modified_gmt = %s WHERE '), 'only allowed columns updated');
        preg_match_all('/BINARY `([A-Za-z_][A-Za-z0-9_]*)` = BINARY %s/', $sql, $matches);
        check(count($matches[1]) === count($this->row), 'every original column is checked byte-exactly');
        foreach ($matches[1] as $index => $column) {
            if ((string) $this->row[$column] !== $values[$index + 3]) { return 0; }
        }
        $this->row['post_content'] = $values[0];
        $this->row['post_modified'] = $values[1];
        $this->row['post_modified_gmt'] = $values[2];
        if ($this->change_after_write) { $this->row['post_content'] = 'Later change'; }
        return 1;
    }
}
$wpdb = new FakeDB();
require __DIR__ . '/../../wordpress_companion/filip-guard-companion.php';
check(isset($GLOBALS['actions']['application_password_did_authenticate']), 'application auth hook');
Filip_Guard_Companion::routes();
if ($scenario !== 'cookie') {
    Filip_Guard_Companion::application_authenticated((object) array('ID' => 7), array('password' => 'fictitious-never-retained'));
}
// Line-oriented bridge for Python-to-PHP protocol integration. No HTTP server.
if ($scenario === 'bridge') {
    $fail_read_after_write = false;
    while (($line = fgets(STDIN)) !== false) {
        $command = json_decode($line, true);
        if (($command['control'] ?? '') === 'quit') { break; }
        if (isset($command['control'])) {
            switch ($command['control']) {
                case 'race': $wpdb->race = true; break;
                case 'verification_failure': $fail_read_after_write = true; break;
                case 'forbidden': $GLOBALS['can_edit'] = false; break;
                case 'stats': break;
                default: throw new Exception('Invalid bridge control');
            }
            echo json_encode(array('queries' => $wpdb->queries, 'content' => $wpdb->row['post_content'])) . "\n";
            flush();
            continue;
        }
        $path = $command['path'] ?? '';
        if (($command['authorization'] ?? '') !== 'Basic ' . base64_encode('editor:fakepassword')) {
            $result = new WP_Error('auth_denied', 'Rejected', array('status' => 401));
        } elseif ($path === '/wp-json/wp/v2/users/me') {
            $result = new WP_REST_Response(array('id' => 7, 'slug' => 'editor', 'name' => 'Editor'), 200);
        } elseif (preg_match('#^/wp-json/filip-guard/v1/resources/(post|page)/([1-9][0-9]{0,9})$#D', $path, $matches)) {
            $request = new Request($command['body'] ?? null, $matches[1], $matches[2]);
            if ($command['method'] === 'GET' && $fail_read_after_write && $wpdb->queries > 0) {
                $fail_read_after_write = false;
                $result = new WP_Error('verification_unavailable', 'Unavailable', array('status' => 503));
            } else {
                $result = $command['method'] === 'GET'
                    ? Filip_Guard_Companion::read($request) : Filip_Guard_Companion::update($request);
            }
        } else {
            $result = new WP_Error('rest_no_route', 'Missing', array('status' => 404));
        }
        $reply = is_wp_error($result)
            ? array('status' => $result->data['status'], 'body' => array('code' => $result->code))
            : array('status' => $result->status, 'body' => $result->data);
        echo json_encode($reply) . "\n";
        flush();
    }
    exit(0);
}
$request = new Request();
$read = Filip_Guard_Companion::read($request);
$gate_errors = array('disabled' => 'fg_disabled', 'production' => 'fg_disabled',
    'http' => 'fg_https_required', 'cookie' => 'fg_application_password_required', 'forbidden' => 'fg_forbidden');
if (isset($gate_errors[$scenario])) {
    code($read, $gate_errors[$scenario]);
    check($wpdb->queries === 0, 'no write on denied request');
    echo "PASS $scenario\n";
    exit(0);
}
check($read instanceof WP_REST_Response && $read->status === 200, 'authorized read');
check($read->headers['Cache-Control'] === 'no-store, private', 'private uncached content');
$data = array('expected_version' => $read->data['version'], 'operation_id' => 'test-operation',
    'proposed_content' => '<p>Updated</p>', 'user_id' => 7);
if ($scenario === 'unsupported_profile') {
    foreach (array('<!-- wp:paragraph --><p>Block</p><!-- /wp:paragraph -->', '[gallery ids="1"]', '<div data-elementor-id="1">Builder</div>') as $unsupported) {
        code(Filip_Guard_Companion::update(new Request(array_merge($data, array('proposed_content' => $unsupported)))), 'fg_compatibility');
    }
    check($wpdb->queries === 0, 'unsupported profiles cannot write');
} elseif ($scenario === 'invalid_payload') {
    foreach (array(array('user_id' => 8), array('user_id' => true),
        array('expected_version' => 'forged'), array('operation_id' => "bad\r\n"),
        array('proposed_content' => '<script>bad</script>'), array('extra' => 'field')) as $change) {
        code(Filip_Guard_Companion::update(new Request(array_merge($data, $change))), 'fg_payload');
    }
    check($wpdb->queries === 0, 'invalid payload cannot write');
} elseif ($scenario === 'stale') {
    $wpdb->row['post_content'] = '<p>Changed</p>';
    code(Filip_Guard_Companion::update(new Request($data)), 'fg_conflict');
    check($wpdb->queries === 0, 'stale request rejected before SQL');
} elseif ($scenario === 'race') {
    $wpdb->race = true;
    code(Filip_Guard_Companion::update(new Request($data)), 'fg_conflict');
    check($wpdb->row['post_title'] === 'Concurrent title', 'concurrent title preserved');
    check($wpdb->row['post_content'] === '<p>Original</p>', 'content not overwritten');
} elseif ($scenario === 'database_error') {
    $wpdb->fail = true;
    code(Filip_Guard_Companion::update(new Request($data)), 'fg_outcome_unknown');
} elseif ($scenario === 'later_change') {
    $wpdb->change_after_write = true;
    code(Filip_Guard_Companion::update(new Request($data)), 'fg_outcome_unknown');
    check($wpdb->row['post_content'] === 'Later change', 'later change preserved');
} elseif ($scenario === 'lost_receipt') {
    $GLOBALS['fail_update_option'] = true;
    code(Filip_Guard_Companion::update(new Request($data)), 'fg_outcome_unknown');
    check($wpdb->row['post_content'] === '<p>Updated</p>', 'write occurred');
    $GLOBALS['fail_update_option'] = false;
    code(Filip_Guard_Companion::update(new Request($data)), 'fg_outcome_unknown');
    check($wpdb->queries === 1, 'pending operation never repeated');
} else {
    $written = Filip_Guard_Companion::update(new Request($data));
    check($written instanceof WP_REST_Response, 'successful write receipt');
    check($written->data['content'] === '<p>Updated</p>', 'updated content');
    foreach (array('post_updated','save_post','wp_after_insert_post') as $hook) {
        check(in_array($hook, $GLOBALS['save_hooks'], true), 'core save lifecycle ' . $hook);
    }
    check($written->data['version'] !== $read->data['version'], 'version changed');
    $replay = Filip_Guard_Companion::update(new Request($data));
    check($replay->data === $written->data && $wpdb->queries === 1, 'exact replay has no write');
    code(Filip_Guard_Companion::update(new Request(array_merge($data,
        array('proposed_content' => 'Different')))), 'fg_operation_mismatch');
    if ($scenario === 'rollback' || $scenario === 'rollback_race') {
        $restore = array('expected_version' => $written->data['version'],
            'operation_id' => 'test-operation:rollback', 'proposed_content' => '<p>Original</p>', 'user_id' => 7);
        if ($scenario === 'rollback_race') { $wpdb->race = true; }
        $restored = Filip_Guard_Companion::update(new Request($restore));
        if ($scenario === 'rollback_race') {
            code($restored, 'fg_conflict');
            check($wpdb->row['post_content'] === '<p>Updated</p>', 'failed rollback did not overwrite content');
        } else {
            check($restored->data['content'] === '<p>Original</p>', 'conditional rollback restores original');
        }
    }
}
echo "PASS $scenario\n";
