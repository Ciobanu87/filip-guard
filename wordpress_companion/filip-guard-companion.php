<?php
/**
 * Plugin Name: FILIP GUARD Conditional Content Endpoint (Gated Candidate)
 * Description: Disabled-by-default candidate with independent test and production admission.
 * Version: 0.2.0
 * Requires PHP: 8.1
 * Requires at least: 6.0
 *
 * Production activation requires matching reviewed operator policy and live validation.
 * Only post_content and modified timestamps are changed.
 * A single byte-exact conditional SQL UPDATE prevents stale-row overwrites.
 * Runs core after-update/save actions for content revisions and hook consumers.
 * Input filters, builder metadata and arbitrary plugin compatibility are not guaranteed.
 */
if (!defined('ABSPATH')) {
    exit;
}

final class Filip_Guard_Companion {
    private static $application_user_id = 0;

    public static function application_authenticated($user, $item) {
        // Do not retain the Application Password item or any credential.
        self::$application_user_id = (int) $user->ID;
    }

    private static function error($code, $status) {
        return new WP_Error($code, 'FILIP GUARD conditional content request rejected.', array('status' => $status));
    }

    private static function target($request) {
        $params = $request->get_url_params();
        $kind = $params['kind'] ?? '';
        $raw_id = $params['id'] ?? '';
        if (!in_array($kind, array('post', 'page'), true)
            || !is_string($raw_id) || !preg_match('/^[1-9][0-9]{0,9}$/D', $raw_id)) {
            return self::error('fg_target', 400);
        }
        return array($kind, (int) $raw_id);
    }

    private static function production_policy() {
        if (!defined('FILIP_GUARD_PRODUCTION_REPAIRS') || FILIP_GUARD_PRODUCTION_REPAIRS !== true
            || !defined('FILIP_GUARD_PRODUCTION_POLICY_JSON') || !is_string(FILIP_GUARD_PRODUCTION_POLICY_JSON)
            || strlen(FILIP_GUARD_PRODUCTION_POLICY_JSON) > 32768) { return false; }
        try {
        $p = json_decode(FILIP_GUARD_PRODUCTION_POLICY_JSON, true);
        $required = array('protocol','profile','site_url','source_commit','wp_version','theme_sha256','companion_sha256',
            'content_selector','resources','approved_at','expires_at','validation_sha256');
        if (!is_array($p)) { return false; }
        $keys = array_keys($p); sort($keys); sort($required);
        if ($keys !== $required || $p['protocol'] !== 'filip-guard-production-v1' || $p['profile'] !== 'classic-html-link-v1'
            || !is_int($p['approved_at']) || !is_int($p['expires_at']) || $p['approved_at'] > time()
            || $p['expires_at'] <= time() || $p['expires_at'] - $p['approved_at'] > 3600
            || $p['site_url'] !== rtrim(home_url(), '/') || !is_string($p['source_commit'])
            || !preg_match('/^[0-9a-f]{40}$/D', $p['source_commit']) || !is_string($p['content_selector'])
            || !preg_match('/^[a-z][a-z0-9-]*#post-\{resource_id\}$/D', $p['content_selector'])
            || !is_array($p['resources']) || count($p['resources']) < 1 || count($p['resources']) > 10) { return false; }
        foreach (array('theme_sha256','companion_sha256','validation_sha256') as $key) {
            if (!is_string($p[$key]) || !preg_match('/^[0-9a-f]{64}$/D', $p[$key]) || $p[$key] === str_repeat('0',64)) { return false; }
        }
        foreach ($p['resources'] as $resource) {
            if (!is_array($resource) || count($resource) !== 2 || !isset($resource['id'],$resource['kind'])
                || !is_int($resource['id']) || $resource['id'] <= 0 || $resource['id'] > 2147483647
                || !in_array($resource['kind'],array('post','page'),true)) { return false; }
        }
        if ($p['wp_version'] !== '7.1.5' || $p['wp_version'] !== get_bloginfo('version') || $p['companion_sha256'] !== hash_file('sha256',__FILE__)
            || $p['theme_sha256'] !== self::theme_fingerprint() || is_multisite()) { return false; }
        if (!function_exists('get_mu_plugins') || !function_exists('get_dropins')) { require_once ABSPATH . 'wp-admin/includes/plugin.php'; }
        if (get_option('active_plugins',array()) !== array('filip-guard-companion/filip-guard-companion.php')
            || get_mu_plugins() !== array() || get_dropins() !== array()) { return false; }
        return $p;
        } catch (Throwable $error) { return false; }
    }

    private static function production_link_change($before,$after,$policy) {
        // Production accepts quoted href value changes only; never arbitrary content replacement.
        if (preg_match('~<\s*(?:base|plaintext|script|style|textarea|title|xmp|iframe|noembed|noframes|template|noscript)\b~i',$before.$after)) { return false; }
        $valid=true; $old=array(); $new=array();
        $mask=function($html,&$values) use (&$valid) {
            return preg_replace_callback('~<a\b(?:"[^"]*"|\'[^\']*\'|[^\'">])*>~is',function($match) use (&$values,&$valid) {
                $tag=$match[0]; $offset=2; $value=null; $count=0;
                // Tokenize attributes; href-looking text inside title/data is data.
                while (preg_match('~\G\s+([A-Za-z_:][A-Za-z0-9_:.-]*)(?:\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s"\'=<>`]+)))?~s',
                    $tag,$attribute,PREG_OFFSET_CAPTURE|PREG_UNMATCHED_AS_NULL,$offset)) {
                    $offset+=strlen($attribute[0][0]);
                    if (strtolower($attribute[1][0])==='href') {
                        $count++;
                        if ($attribute[2][0]!==null) { $value=$attribute[2]; }
                        elseif ($attribute[3][0]!==null) { $value=$attribute[3]; }
                        else { $valid=false; }
                    }
                }
                if (!preg_match('~^\s*/?>$~D',substr($tag,$offset)) || $count>1) { $valid=false; }
                if ($count===0) { return $tag; }
                if ($value===null) { $valid=false; return $tag; }
                $values[]=$value[0];
                return substr_replace($tag,'FILIP_GUARD_REVIEWED_HREF',$value[1],strlen($value[0]));
            },$html);
        };
        $a=$mask($before,$old); $b=$mask($after,$new);
        if (!$valid || !is_string($a) || $a !== $b || count($old)!==count($new)) { return false; }
        $changes=0;
        foreach ($new as $index=>$href) {
            if ($href === $old[$index]) { continue; }
            $changes++; $url=html_entity_decode($href,ENT_QUOTES|ENT_HTML5,'UTF-8');
            if (!$url || preg_match('~[\x00-\x20\x7f\\\\]~',$url)) { return false; }
            $parts=wp_parse_url($url);
            if ($parts === false) { return false; }
            if (isset($parts['scheme']) || isset($parts['host'])) {
                $origin=wp_parse_url($policy['site_url']);
                if (($parts['scheme']??'')!=='https' || ($parts['host']??'')!==$origin['host']
                    || isset($parts['user']) || isset($parts['pass']) || (isset($parts['port']) && $parts['port']!==443)) { return false; }
            } elseif (strpos($url,'//')===0 || strpos($url,':')!==false) { return false; }
        }
        return $changes>=1 && $changes<=20;
    }

    private static function authenticated() {
        if (wp_get_environment_type() === 'production') {
            // Do not hash theme files for unauthenticated requests.
            if (!defined('FILIP_GUARD_PRODUCTION_REPAIRS') || FILIP_GUARD_PRODUCTION_REPAIRS !== true
                || !defined('FILIP_GUARD_PRODUCTION_POLICY_JSON')) { return self::error('fg_disabled',403); }
        } elseif (!defined('FILIP_GUARD_TEST_REPAIRS') || FILIP_GUARD_TEST_REPAIRS !== true
            || !in_array(wp_get_environment_type(), array('local', 'development', 'staging'), true)) {
            return self::error('fg_disabled', 403);
        }
        if (!is_ssl()) {
            return self::error('fg_https_required', 403);
        }
        $user_id = get_current_user_id();
        if ($user_id <= 0 || self::$application_user_id !== $user_id) {
            return self::error('fg_application_password_required', 401);
        }
        if (wp_get_environment_type()==='production' && self::production_policy()===false) { return self::error('fg_disabled',403); }
        return true;
    }

    public static function permission($request) {
        $authenticated = self::authenticated();
        if ($authenticated !== true) { return $authenticated; }
        $target = self::target($request);
        if (is_wp_error($target)) {
            return $target;
        }
        if (wp_get_environment_type() === 'production') {
            $policy=self::production_policy(); $admitted=false;
            if ($policy===false || !current_user_can('manage_options')) { return self::error('fg_disabled',403); }
            foreach ($policy['resources'] as $resource) {
                if ($resource['kind']===$target[0] && $resource['id']===$target[1]) { $admitted=true; }
            }
            $metadata=get_post_custom_keys($target[1]);
            if ($metadata===null) { $metadata=array(); }
            if (!$admitted || !is_array($metadata) || array_diff($metadata,array('_edit_lock','_edit_last','_wp_old_slug','_wp_page_template','_thumbnail_id'))) {
                return self::error('fg_profile',403);
            }
        }
        clean_post_cache($target[1]);
        if (!current_user_can('edit_post', $target[1])) {
            return self::error('fg_forbidden', 403);
        }
        return true;
    }

    public static function ownership_permission($request) {
        $authenticated = self::authenticated();
        if ($authenticated !== true) { return $authenticated; }
        return current_user_can('manage_options') ? true : self::error('fg_site_owner_required', 403);
    }

    public static function ownership($request) {
        $permission = self::ownership_permission($request);
        if ($permission !== true) { return $permission; }
        return self::response(array('protocol' => 'filip-guard-cas-v1',
            'user_id' => get_current_user_id(), 'can_manage_site' => true));
    }

    private static function row($kind, $id) {
        global $wpdb;
        $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$wpdb->posts} WHERE ID = %d", $id), ARRAY_A);
        if (!is_array($row) || ($row['post_type'] ?? '') !== $kind
            || !in_array($row['post_status'] ?? '', array('publish', 'draft', 'pending', 'private'), true)) {
            return self::error('fg_resource', 404);
        }
        if (!is_string($row['post_content']) || strlen($row['post_content']) > 1000000) {
            return self::error('fg_size', 413);
        }
        return $row;
    }

    private static function version($row) {
        ksort($row);
        $encoded = wp_json_encode($row);
        return $encoded === false ? false : hash('sha256', $encoded);
    }

    private static function snapshot($row) {
        $version = self::version($row);
        if ($version === false) {
            return self::error('fg_encoding', 500);
        }
        return array('protocol' => 'filip-guard-cas-v1',
            'resource_id' => (int) $row['ID'], 'resource_type' => $row['post_type'],
            'user_id' => get_current_user_id(), 'can_edit' => true,
            'content' => $row['post_content'], 'version' => $version);
    }

    private static function response($snapshot) {
        if (is_wp_error($snapshot)) {
            return $snapshot;
        }
        $response = new WP_REST_Response($snapshot, 200);
        $response->header('Cache-Control', 'no-store, private');
        return $response;
    }

    public static function read($request) {
        $permission = self::permission($request);
        if ($permission !== true) {
            return $permission;
        }
        list($kind, $id) = self::target($request);
        $row = self::row($kind, $id);
        return is_wp_error($row) ? $row : self::response(self::snapshot($row));
    }

    private static function theme_fingerprint() {
        // Hash actual reviewed theme files, not merely a version label. Bound work.
        $theme = wp_get_theme();
        $roots = array('template' => $theme->get_template_directory(),
            'stylesheet' => $theme->get_stylesheet_directory());
        $manifest = array(); $bytes = 0; $files = 0; $seen = array();
        $started = microtime(true);
        foreach ($roots as $label => $root) {
            if (!is_string($root) || is_link($root) || !is_dir($root)) { return null; }
            $root = realpath($root);
            if (isset($seen[$root])) { continue; }
            $seen[$root] = true;
            $iterator = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root,
                FilesystemIterator::SKIP_DOTS));
            foreach ($iterator as $file) {
                $files++;
                if ($files > 1000 || microtime(true) - $started > 2) { return null; }
                if ($file->isLink()) { return null; }
                if (!$file->isFile()) { continue; }
                $bytes += $file->getSize();
                if ($files > 1000 || $bytes > 10000000) { return null; }
                $digest = hash_file('sha256', $file->getPathname());
                if ($digest === false) { return null; }
                $relative = substr($file->getPathname(), strlen($root) + 1);
                $manifest[$label . '/' . str_replace(DIRECTORY_SEPARATOR, '/', $relative)] = $digest;
            }
        }
        if (!$manifest) { return null; }
        ksort($manifest);
        return hash('sha256', wp_json_encode($manifest));
    }

    public static function compatibility_permission($request) {
        $owner = self::ownership_permission($request);
        return $owner === true ? self::permission($request) : $owner;
    }

    public static function compatibility($request) {
        // Authenticated, owner-only, read-only inventory. Never a write admission.
        $permission = self::compatibility_permission($request);
        if ($permission !== true) { return $permission; }
        list($kind, $id) = self::target($request);
        $row = self::row($kind, $id);
        if (is_wp_error($row)) { return $row; }
        try {
            if (!function_exists('get_mu_plugins') || !function_exists('get_dropins')) {
                require_once ABSPATH . 'wp-admin/includes/plugin.php';
            }
            $metadata = get_post_custom_keys($id);
            if ($metadata === null) { $metadata = array(); }
            $plugins = get_option('active_plugins', array());
            $mu = array_keys(get_mu_plugins()); $dropins = array_keys(get_dropins());
            foreach (array($plugins, $mu, $dropins, $metadata) as $items) {
                if (!is_array($items) || count($items) > 200) { return self::error('fg_inventory', 409); }
                foreach ($items as $item) {
                    if (!is_string($item) || strlen($item) > 256) { return self::error('fg_inventory', 409); }
                }
            }
            $snapshot = self::snapshot($row);
            if (is_wp_error($snapshot)) { return $snapshot; }
            $evidence = array('resource_type' => $kind, 'resource_id' => $id,
                'revision' => $snapshot['version'], 'content_sha256' => hash('sha256', $row['post_content']),
                'observed_at' => time(), 'environment' => wp_get_environment_type(),
                'wp_version' => get_bloginfo('version'), 'multisite' => is_multisite(),
                'active_plugins' => array_values($plugins), 'mu_plugins' => $mu, 'dropins' => $dropins,
                'metadata_keys' => array_values($metadata), 'theme_sha256' => self::theme_fingerprint(),
                'companion_sha256' => hash_file('sha256',__FILE__),
                'production_policy_sha256' => wp_get_environment_type()==='production' ? hash('sha256',FILIP_GUARD_PRODUCTION_POLICY_JSON) : null);
            return self::response(array('protocol' => 'filip-guard-compatibility-v1',
                'snapshot' => $snapshot, 'evidence' => $evidence));
        } catch (Throwable $error) {
            return self::error('fg_inventory', 409);
        }
    }

    private static function compatible_content($content) {
        // Classic HTML only. This is a restriction, never production authorization.
        return is_string($content) && !preg_match('~<!--\s*wp:|\[/?[A-Za-z][A-Za-z0-9_-]*(?:\s[^\]]*)?/?\]|data-(?:elementor|vc|fl)-|et_pb_|fl-builder~i', $content);
    }

    public static function update($request) {
        global $wpdb;
        $permission = self::permission($request);
        if ($permission !== true) {
            return $permission;
        }
        list($kind, $id) = self::target($request);
        if (strlen($request->get_body()) > 1100000) {
            return self::error('fg_size', 413);
        }
        $data = $request->get_json_params();
        $keys = is_array($data) ? array_keys($data) : array();
        sort($keys);
        if ($keys !== array('expected_version', 'operation_id', 'proposed_content', 'user_id')
            || !is_int($data['user_id']) || $data['user_id'] !== get_current_user_id()
            || !is_string($data['expected_version']) || !preg_match('/^[0-9a-f]{64}$/D', $data['expected_version'])
            || !is_string($data['operation_id']) || !preg_match('/^[A-Za-z0-9:_-]{1,96}$/D', $data['operation_id'])
            || !is_string($data['proposed_content']) || strlen($data['proposed_content']) > 1000000
            || wp_kses_post($data['proposed_content']) !== $data['proposed_content']) {
            return self::error('fg_payload', 400);
        }
        $row = self::row($kind, $id);
        if (is_wp_error($row)) {
            return $row;
        }
        if (!self::compatible_content($row['post_content']) || !self::compatible_content($data['proposed_content'])) {
            return self::error('fg_compatibility', 409);
        }
        if (wp_get_environment_type()==='production') {
            $policy=self::production_policy();
            if ($policy===false || !self::production_link_change($row['post_content'],$data['proposed_content'],$policy)) { return self::error('fg_profile',403); }
        }
        // Unique option reservation is durable and survives lost replies/process restarts.
        // Pending reservations are never retried automatically after an uncertain outcome.
        $option = 'fg_cas_' . hash('sha256', get_current_user_id() . ':' . $data['operation_id']);
        $digest = hash('sha256', wp_json_encode(array($kind, $id, $data)));
        $previous = get_option($option, false);
        if ($previous !== false) {
            if (!is_array($previous) || !isset($previous['digest']) || !hash_equals($previous['digest'], $digest)) {
                return self::error('fg_operation_mismatch', 409);
            }
            if (($previous['state'] ?? '') === 'complete') {
                return self::response($previous['receipt']);
            }
            return self::error('fg_outcome_unknown', 409);
        }
        $version = self::version($row);
        if ($version === false || !hash_equals($version, $data['expected_version'])) {
            return self::error('fg_conflict', 409);
        }
        if ($row['post_content'] === $data['proposed_content']) {
            return self::error('fg_no_change', 400);
        }
        if (!add_option($option, array('digest' => $digest, 'state' => 'pending'), '', false)) {
            return self::error('fg_outcome_unknown', 409);
        }
        $new_row = $row;
        $new_row['post_content'] = $data['proposed_content'];
        $new_row['post_modified'] = current_time('mysql');
        $new_row['post_modified_gmt'] = current_time('mysql', true);
        $where = array();
        $values = array($new_row['post_content'], $new_row['post_modified'], $new_row['post_modified_gmt']);
        foreach ($row as $column => $value) {
            if (!preg_match('/^[A-Za-z_][A-Za-z0-9_]*$/D', $column)) {
                return self::error('fg_schema', 500);
            }
            if ($value === null) {
                $where[] = "`{$column}` IS NULL";
            } else {
                // BINARY avoids case-insensitive collation and trailing-space matches.
                $where[] = "BINARY `{$column}` = BINARY %s";
                $values[] = (string) $value;
            }
        }
        // Single SQL CAS: a concurrent change to ANY selected post column wins.
        $sql = "UPDATE {$wpdb->posts} SET post_content = %s, post_modified = %s, post_modified_gmt = %s WHERE "
            . implode(' AND ', $where);
        if (!current_user_can('edit_post', $id)) {
            return self::error('fg_forbidden', 403);
        }
        $affected = $wpdb->query($wpdb->prepare($sql, $values));
        if ($affected === false) {
            return self::error('fg_outcome_unknown', 503);
        }
        if ($affected !== 1) {
            return self::error('fg_conflict', 409);
        }
        clean_post_cache($id);
        $observed = self::row($kind, $id);
        if (is_wp_error($observed) || self::version($observed) !== self::version($new_row)) {
            return self::error('fg_outcome_unknown', 409);
        }
        // Preserve the atomic SQL guard, then run the core after-update lifecycle.
        // Input filters/metadata updates are not emulated: only reviewed raw content
        // passing wp_kses_post is supported. Any callback mutation invalidates receipt.
        try {
            $before_post = new WP_Post((object) $row);
            $after_post = new WP_Post((object) $observed);
            wp_transition_post_status($after_post->post_status, $before_post->post_status, $after_post);
            do_action("edit_post_{$kind}", $id, $after_post);
            do_action('edit_post', $id, $after_post);
            do_action('post_updated', $id, $after_post, $before_post);
            do_action("save_post_{$kind}", $id, $after_post, true);
            do_action('save_post', $id, $after_post, true);
            do_action('wp_insert_post', $id, $after_post, true);
            wp_after_insert_post($after_post, true, $before_post);
        } catch (Throwable $error) {
            return self::error('fg_outcome_unknown', 503);
        }
        clean_post_cache($id);
        $after_hooks = self::row($kind, $id);
        if (is_wp_error($after_hooks) || self::version($after_hooks) !== self::version($new_row)) {
            return self::error('fg_outcome_unknown', 409);
        }
        $receipt = self::snapshot($after_hooks);
        if (is_wp_error($receipt) || !update_option($option,
            array('digest' => $digest, 'state' => 'complete', 'receipt' => $receipt), false)) {
            return self::error('fg_outcome_unknown', 503);
        }
        return self::response($receipt);
    }

    public static function routes() {
        register_rest_route('filip-guard/v1', '/ownership', array(
            'methods' => 'GET', 'callback' => array(__CLASS__, 'ownership'),
            'permission_callback' => array(__CLASS__, 'ownership_permission'),
        ));
        register_rest_route('filip-guard/v1', '/resources/(?P<kind>post|page)/(?P<id>[1-9][0-9]{0,9})/compatibility', array(
            'methods' => 'GET', 'callback' => array(__CLASS__, 'compatibility'),
            'permission_callback' => array(__CLASS__, 'compatibility_permission'),
        ));
        register_rest_route('filip-guard/v1', '/resources/(?P<kind>post|page)/(?P<id>[1-9][0-9]{0,9})', array(
            array('methods' => 'GET', 'callback' => array(__CLASS__, 'read'),
                'permission_callback' => array(__CLASS__, 'permission')),
            array('methods' => 'POST', 'callback' => array(__CLASS__, 'update'),
                'permission_callback' => array(__CLASS__, 'permission')),
        ));
    }
}
add_action('application_password_did_authenticate', array('Filip_Guard_Companion', 'application_authenticated'), 10, 2);
add_action('rest_api_init', array('Filip_Guard_Companion', 'routes'));
