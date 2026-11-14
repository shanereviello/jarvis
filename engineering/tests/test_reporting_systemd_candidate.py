from pathlib import Path

ROOT=Path(__file__).parents[1]/'systemd'


def text(name):return (ROOT/name).read_text()


def test_adapter_is_bridge_only_and_does_not_receive_repo_or_provider_secret():
    unit=text('rras-codex-runtime.service')
    assert 'User=rras-codex-adapter' in unit and 'Group=rras-codex-adapter' in unit
    assert 'IPAddressDeny=any' in unit and 'IPAddressAllow=172.19.0.0/16' in unit
    assert 'ProtectSystem=strict' in unit
    assert 'After=network.target docker.service rras-engineering-history.service' in unit
    assert 'Wants=docker.service' in unit and 'WantedBy=multi-user.target' in unit
    assert 'ReadWritePaths=/run/rras-codex-runtime' in unit
    assert '--bind 172.19.0.1 --port 8766' in unit
    assert '/srv/git/jarvis' not in unit and 'LoadCredential' not in unit and 'OPENAI_API_KEY=' not in unit
    assert 'ConditionPathExists=/etc/rras-engineering/codex-runtime/host-runtime-enabled' in unit


def test_only_native_coding_service_gets_the_single_provider_credential():
    coding=text('rras-codex-coding@.service')
    source=text('rras-codex-source@.service')
    assert 'User=rras-codex-native' in coding and 'LoadCredential=openai-api-key:' in coding
    assert 'codex_app_server_entry.py' in coding and 'StandardInput=socket' in coding
    assert 'User=rras-codex-native' in source and 'StandardInput=socket' in source
    assert 'LoadCredential' not in source and 'RRAS_OPENAI_API_KEY' not in source
    assert 'RestrictAddressFamilies=AF_UNIX' in source
    assert 'ReadOnlyPaths=/var/lib/rras-codex-native/codex' in source


def test_socket_templates_and_passive_capture_timers_are_disabled_candidates():
    for name,template in [('rras-codex-coding.socket','rras-codex-coding@.service'),
                          ('rras-codex-source.socket','rras-codex-source@.service')]:
        unit=text(name)
        assert 'Accept=yes' in unit and 'SocketMode=0600' in unit
        assert 'Service=' not in unit and (ROOT/template).is_file()
        assert 'ConditionPathExists=/etc/rras-engineering/codex-runtime/host-runtime-enabled' in unit
    for name in ('rras-codex-capture.timer','rras-hermes-history.timer'):
        unit=text(name)
        assert 'OnUnitActiveSec=1min' in unit
        assert 'ConditionPathExists=/etc/rras-engineering/codex-runtime/host-runtime-enabled' in unit
    assert '0750 rras-codex-adapter rras-codex-adapter' in text('rras-codex-runtime.conf')


def test_handoff_delivery_is_scoped_to_the_private_adapter_and_network():
    service=text('rras-codex-handoff-delivery.service')
    timer=text('rras-codex-handoff-delivery.timer')
    assert 'User=rras-codex-adapter' in service and 'Type=oneshot' in service
    assert 'runtime_handoff_delivery.py --config /var/lib/rras-codex-adapter/handoff-delivery.json' in service
    assert 'ProtectSystem=strict' in service and 'NoNewPrivileges=yes' in service
    assert 'IPAddressDeny=any' in service and 'IPAddressAllow=172.19.0.0/16' in service
    assert 'LoadCredential=' not in service and 'OPENAI_API_KEY=' not in service
    assert 'Unit=rras-codex-handoff-delivery.service' in timer
    for unit in (service,timer):
        assert 'ConditionPathExists=/var/lib/rras-codex-adapter/handoff-delivery.json' in unit


def test_observer_timers_use_fixed_private_configuration_and_no_provider_credentials():
    for name,entry,config in (
        ('rras-codex-handoff-history','handoff_history_http.py','handoff-history.json'),
        ('rras-codex-linear-observer','linear_observer_http.py','linear-observer.json'),
    ):
        service=text(name+'.service');timer=text(name+'.timer')
        assert 'User=rras-codex-adapter' in service and 'Type=oneshot' in service
        assert entry+' --config /var/lib/rras-codex-adapter/'+config in service
        assert 'IPAddressDeny=any' in service and 'IPAddressAllow=172.19.0.0/16' in service
        assert 'LoadCredential=' not in service and 'OPENAI_API_KEY=' not in service
        assert 'Unit='+name+'.service' in timer
        for unit in (service,timer):
            assert 'ConditionPathExists=/var/lib/rras-codex-adapter/'+config in unit
