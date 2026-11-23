<?php
/** Test fixture MU-plugin: records real hooks and injects controlled side effects. */
foreach (array('post_updated', 'save_post', 'wp_after_insert_post') as $hook) {
    add_action($hook, function($id) use ($hook) {
        if (get_post_type($id) !== 'post') { return; }
        $events = get_option('fg_fixture_events', array());
        $events[] = array('hook' => $hook, 'id' => (int) $id);
        update_option('fg_fixture_events', $events, false);
    }, 100, 1);
}
add_action('save_post', function($id) {
    if ((int) get_option('fg_fixture_mutate_post', 0) === (int) $id) {
        delete_option('fg_fixture_mutate_post');
        wp_update_post(array('ID' => $id, 'post_title' => 'Fixture plugin changed title'));
    }
}, 200, 1);
add_filter('query', function($sql) {
    global $wpdb;
    if (strpos($sql, "UPDATE {$wpdb->posts} SET post_content = ") === 0 && strpos($sql, 'BINARY `ID`') !== false) {
        $id = (int) get_option('fg_fixture_sql_race', 0);
        if ($id > 0) {
            delete_option('fg_fixture_sql_race');
            $wpdb->update($wpdb->posts, array('post_title' => 'Concurrent at SQL'), array('ID' => $id));
        }
    }
    return $sql;
});

// Fixture diagnostics expose no credentials and are never installed outside tests.
add_action('rest_api_init', function() {
    register_rest_route('fg-fixture/v1', '/runtime', array(
        'methods' => 'GET',
        'permission_callback' => function() { return current_user_can('edit_posts'); },
        'callback' => function() {
            return array('enabled' => defined('FILIP_GUARD_TEST_REPAIRS') && FILIP_GUARD_TEST_REPAIRS === true,
                'environment' => wp_get_environment_type(), 'sapi' => PHP_SAPI,
                'opcache' => ini_get('opcache.enable'));
        },
    ));
});
