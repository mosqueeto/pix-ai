#!/usr/bin/perl
#
# pix-init.cgi — Web-based gallery initialization interface
#
# States:
#   idle    — no _pix directory or no .running / index.json
#   running — _pix/.running sentinel exists (init in progress)
#   done    — _pix/index.json exists → redirect to index.html
#   error   — .running gone but no index.json (init failed)
#
# Endpoints:
#   GET /pix-init.cgi              — show status page
#   GET /pix-init.cgi?action=start — fork background init, show progress page
#   GET /pix-init.cgi?action=status — JSON status for AJAX polling
#
use strict;
use warnings;
use File::Basename  qw(dirname basename);
use File::Path      qw(make_path);
use Cwd             qw(abs_path);
use JSON::PP;

# Gallery directory = the directory containing this CGI script
my $gallery  = dirname(abs_path($ENV{SCRIPT_FILENAME} || $0));
my $pix      = "$gallery/_pix";
my $index    = "$pix/index.json";
my $log      = "$pix/log.txt";
my $running  = "$pix/.running";
my $init_pl  = "$gallery/pix-init.pl";

# Parse query string
my %Q;
for (split /&/, $ENV{QUERY_STRING} // '') {
    my ($k, $v) = split /=/, $_, 2;
    $Q{$k} = $v // '' if defined $k;
}
my $action = $Q{action} // '';

# ── JSON status endpoint ───────────────────────────────────────────────────────

if ($action eq 'status') {
    print "Content-Type: application/json\r\n\r\n";
    my $state = state();
    my $tail  = log_tail(60);
    print JSON::PP->new->encode({ state => $state, log => $tail });
    exit;
}

# ── Start initialization ───────────────────────────────────────────────────────

if ($action eq 'start') {
    if (state() eq 'idle') {
        make_path($pix);
        # Create sentinel before forking so status shows 'running' immediately
        if (open(my $fh, '>', $running)) { close $fh; }
        start_worker();
    }
    print "Content-Type: text/html\r\n\r\n";
    print '<script>location.href="pix-init.cgi"</script>';
    exit;
}

# ── Default: HTML status page ──────────────────────────────────────────────────

print "Content-Type: text/html; charset=utf-8\r\n\r\n";

my $st = state();

if ($st eq 'done') {
    unlink $running;
    print '<script>location.href="index.html"</script>';
    exit;
}

print html_page($st);

# ── Helpers ───────────────────────────────────────────────────────────────────

sub state {
    return 'done'    if -f $index;
    return 'running' if -f $running;
    return 'error'   if -f $log && !-f $running;  # prev attempt left a log
    return 'idle';
}

sub log_tail {
    my $n = shift // 60;
    return '' unless open(my $fh, '<', $log);
    local $/;  my $all = <$fh>;  close $fh;
    my @lines = split /\n/, $all;
    my $start = @lines > $n ? @lines - $n : 0;
    return join("\n", @lines[$start .. $#lines]);
}

sub start_worker {
    # Double-fork: grandchild is adopted by init(1), survives CGI exit
    my $pid = fork();
    if (!defined $pid) { warn "fork: $!"; return; }
    if ($pid == 0) {
        my $pid2 = fork();
        if (!defined $pid2) { exit 1; }
        if ($pid2 == 0) {
            # Grandchild: run the init script
            open(STDIN,  '<', '/dev/null');
            open(STDOUT, '>', $log);
            open(STDERR, '>&STDOUT');
            $| = 1;
            exec($^X, $init_pl, $gallery);
            exit 1;
        }
        exit 0;
    }
    waitpid($pid, 0);
}

sub html_page {
    my $st = shift;

    if ($st eq 'idle' || $st eq 'error') {
        my $err = $st eq 'error'
            ? '<p class="msg-err">A previous initialization attempt failed.  '
              . 'Check the log below, then try again.</p>'
              . '<pre class="log-box">' . esc(log_tail(30)) . '</pre>'
            : '';
        return <<"HTML";
<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>Pix — Initialize</title><style>
body{font-family:system-ui,sans-serif;background:#1a1a1a;color:#ddd;
     max-width:640px;margin:80px auto;padding:0 1.5rem;text-align:center}
h1{font-weight:300;color:#aaa;margin-bottom:1.2rem}
p{color:#888;margin:.6rem 0;line-height:1.6}
pre{background:#111;color:#7f7;padding:.7rem 1.1rem;border-radius:4px;
    text-align:left;display:inline-block;margin:.7rem 0;font-size:.85rem}
.log-box{display:block;width:100%;max-height:200px;overflow-y:auto}
.msg-err{color:#f88}
.btn{background:#336;border:1px solid #669;color:#cce;padding:.6rem 1.8rem;
     border-radius:4px;cursor:pointer;font-size:1rem;margin-top:1.2rem}
.btn:hover{background:#447}
</style></head><body>
<h1>Gallery Not Initialized</h1>
$err
<p>For large collections, run from the command line:</p>
<pre>perl pix-init.pl /path/to/gallery</pre>
<p>Or initialize through the browser (may take a while for many photos):</p>
<form action="pix-init.cgi" method="get">
<input type="hidden" name="action" value="start">
<button class="btn" type="submit">Initialize Gallery</button>
</form>
</body></html>
HTML
    }

    # state eq 'running'
    return <<'HTML';
<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>Pix — Initializing…</title><style>
body{font-family:system-ui,sans-serif;background:#1a1a1a;color:#ddd;
     max-width:740px;margin:60px auto;padding:0 1.5rem}
h1{font-weight:300;color:#aaa}
#status{color:#888;margin:.4rem 0 1rem}
#log{background:#111;color:#7f7;padding:.9rem;height:400px;overflow-y:auto;
     border-radius:4px;font-size:12px;font-family:monospace;white-space:pre-wrap;
     word-break:break-all}
</style></head><body>
<h1>Initializing Gallery…</h1>
<p id="status">Processing photos — please wait</p>
<div id="log">Starting…</div>
<script>
(function poll() {
  fetch('pix-init.cgi?action=status')
    .then(r => r.json())
    .then(d => {
      var el = document.getElementById('log');
      el.textContent = d.log || '(waiting for output\u2026)';
      el.scrollTop = el.scrollHeight;
      if (d.state === 'done') {
        document.getElementById('status').textContent = 'Done! Redirecting\u2026';
        setTimeout(() => { location.href = 'index.html'; }, 900);
      } else {
        setTimeout(poll, 2000);
      }
    })
    .catch(() => setTimeout(poll, 3000));
})();
</script>
</body></html>
HTML
}

sub esc {
    my $s = shift // '';
    $s =~ s/&/&amp;/g; $s =~ s/</&lt;/g; $s =~ s/>/&gt;/g;
    return $s;
}
