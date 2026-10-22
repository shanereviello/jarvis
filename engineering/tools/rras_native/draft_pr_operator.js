(async function draftPrOperator({tools, bridge, release, packagePath, workspace}) {
  // Trusted frontend only. The packaged entrypoint embeds the reviewed bridge;
  // worker text never supplies callbacks, tool names or shell command fragments.
  if (typeof bridge !== 'function' || !/^\/opt\/rras-engineering\/releases\/workflow-[0-9a-f]{12}$/.test(release || '')) {
    throw new Error('protected_release_required');
  }
  const required = ['exec_command', 'write_stdin', 'mcp__codex_apps__github_fetch',
    'mcp__codex_apps__github_create_pull_request', 'codex_app__attach_artifact'];
  if (!required.every(name => typeof tools?.[name] === 'function')) throw new Error('frontend_tools_required');
  for (const path of [packagePath, ...(workspace === undefined ? [] : [workspace])]) {
    if (typeof path !== 'string' || !path.startsWith('/') || path.includes('\0') || path.length > 4096) throw new Error('absolute_operator_paths_required');
  }
  const quote = value => "'" + value.replaceAll("'", "'\"'\"'") + "'";
  const cli = async (action, data) => {
    if (!['prepare', 'arm', 'complete', 'unknown'].includes(action)) throw new Error('cli_action_refused');
    const argv = ['/opt/rras-engineering/releases/native-10/venv/bin/python', '-I', '-B',
      release + '/entrypoints/draft-pr.py', action, '--package', packagePath];
    if (workspace !== undefined) argv.push('--workspace', workspace);
    if (data !== undefined) {
      const raw = JSON.stringify(data);
      if (typeof raw !== 'string' || raw.length > 65536) throw new Error('bounded_cli_metadata_required');
      argv.push('--data', raw);
    }
    let reply = await tools.exec_command({cmd: argv.map(quote).join(' '),
      sandbox_permissions: 'require_escalated',
      justification: 'Run the protected named-operator draft-PR helper for the selected reviewed handoff.',
      max_output_tokens: 4096, yield_time_ms: 1000});
    let output = '';
    const started = Date.now();
    while (true) {
      if (typeof reply?.output !== 'string') throw new Error('host_cli_shape');
      output += reply.output;
      if (output.length > 65536) throw new Error('host_cli_output_bound');
      if (reply.exit_code !== undefined && reply.exit_code !== null) {
        if (reply.exit_code !== 0) throw new Error('host_cli_refused');
        break;
      }
      if (typeof reply.session_id !== 'number') throw new Error('host_cli_shape');
      if (Date.now() - started > 45000) throw new Error('host_cli_still_running_preserve_fence');
      // Resume the same process only. Never rerun an action after a lost response.
      reply = await tools.write_stdin({session_id: reply.session_id, chars: '', yield_time_ms: 1000, max_output_tokens: 4096});
    }
    const result = JSON.parse(output);
    if (!result || typeof result !== 'object' || Array.isArray(result)) throw new Error('host_cli_json_shape');
    if (result.operator_binding_protocol !== 1) throw new Error('host_cli_protocol_mismatch');
    return result;
  };
  const github = (operation, args) => {
    if (operation === 'fetch') return tools.mcp__codex_apps__github_fetch(args);
    if (operation === 'create_pull_request') return tools.mcp__codex_apps__github_create_pull_request(args);
    throw new Error('github_operation_refused');
  };
  const attach = async url => {
    const result = await tools.codex_app__attach_artifact({artifact_type: 'pull_request', url});
    if (result?.isError) throw new Error('attachment_failed');
    return result;
  };
  return await bridge({cli, github, attach});
})
