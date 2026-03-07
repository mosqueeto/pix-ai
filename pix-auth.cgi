#!/usr/bin/perl
#
# pix-auth.cgi — password gate for the pix gallery
#
# Endpoints:
#   GET  pix-auth.cgi              — show login form (or redirect if already authed)
#   POST pix-auth.cgi              — submit password
#   GET  pix-auth.cgi?action=check — JSON {ok:true/false} for JS polling
#   GET  pix-auth.cgi?action=logout— clear session and redirect to login
#
# Setup (run once from command line):
#   perl pix-auth.cgi --set-password YOURPASSWORD
#
use strict;
use warnings;
use Digest::SHA  qw(sha256_hex);
use File::Path   qw(make_path);
use File::Basename qw(dirname);
use Cwd          qw(abs_path);

my $gallery  = dirname(abs_path($ENV{SCRIPT_FILENAME} || $0));
my $pix      = "$gallery/_pix";
my $sessdir  = "$pix/.sessions";
my $passwdf  = "$pix/.pix-passwd";

my $COOKIE          = 'pix_session';
my $SESSION_MAX_AGE = 30 * 86400;   # 30 days

# ── Command-line: set password ────────────────────────────────────────────────

if (@ARGV && $ARGV[0] eq '--set-password') {
    my $pw = $ARGV[1] // '';
    die "Usage: perl pix-auth.cgi --set-password PASSWORD\n" unless length $pw;
    make_path($pix);
    open(my $fh, '>', $passwdf) or die "Cannot write $passwdf: $!\n";
    print $fh sha256_hex($pw), "\n";
    close $fh;
    print "Password set.\n";
    exit;
}

# ── CGI ───────────────────────────────────────────────────────────────────────

my $method = $ENV{REQUEST_METHOD} // 'GET';
my %Q = parse_qs(
    $method eq 'POST'
        ? do { read(STDIN, my $b, $ENV{CONTENT_LENGTH} // 0); $b }
        : $ENV{QUERY_STRING} // ''
);
my $action = $Q{action} // '';

# ── JSON auth-check (called by pix.js on every page load) ────────────────────

if ($action eq 'check') {
    print "Content-Type: application/json\r\n\r\n";
    print valid_session() ? '{"ok":true}' : '{"ok":false}';
    exit;
}

# ── Logout ────────────────────────────────────────────────────────────────────

if ($action eq 'logout') {
    del_session(cookie_token());
    print "Content-Type: text/html\r\n";
    print "Set-Cookie: $COOKIE=; Path=/; Max-Age=0\r\n\r\n";
    print redirect_js('pix-auth.cgi');
    exit;
}

# ── Login POST ────────────────────────────────────────────────────────────────

if ($method eq 'POST') {
    if (check_password($Q{password} // '')) {
        my $tok = new_session();
        print "Content-Type: text/html\r\n";
        print "Set-Cookie: $COOKIE=$tok; Path=/; HttpOnly; SameSite=Strict; Max-Age=$SESSION_MAX_AGE\r\n\r\n";
        print redirect_js('index.html');
    } else {
        print "Content-Type: text/html; charset=utf-8\r\n\r\n";
        print login_page('Incorrect password.');
    }
    exit;
}

# ── GET: redirect if already authed, else show login ─────────────────────────

if (valid_session()) {
    print "Content-Type: text/html\r\n\r\n";
    print redirect_js('index.html');
} else {
    print "Content-Type: text/html; charset=utf-8\r\n\r\n";
    my $hint = -f $passwdf ? ''
        : 'No password configured. Run: perl pix-auth.cgi --set-password PASSWORD';
    print login_page($hint);
}

# ── Helpers ───────────────────────────────────────────────────────────────────

sub parse_qs {
    my %h;
    for (split /&/, shift // '') {
        my ($k, $v) = split /=/, $_, 2;
        next unless defined $k;
        for ($k, $v) { $_ //= ''; s/\+/ /g; s/%([0-9A-Fa-f]{2})/chr hex $1/ge; }
        $h{$k} = $v;
    }
    %h;
}

sub cookie_token {
    my $c = $ENV{HTTP_COOKIE} // '';
    return $c =~ /(?:^|;\s*)\Q$COOKIE\E=([0-9a-f]{64})/ ? $1 : '';
}

sub valid_session {
    my $tok = cookie_token() or return 0;
    my $f   = "$sessdir/$tok";
    return 0 unless -f $f;
    open(my $fh, '<', $f) or return 0;
    my $exp = <$fh>; close $fh; chomp($exp //= 0);
    return time() < $exp;
}

sub new_session {
    make_path($sessdir);

    # Protect sessions dir from direct web access
    my $ha = "$sessdir/.htaccess";
    unless (-f $ha) {
        if (open(my $fh, '>', $ha)) { print $fh "Require all denied\n"; close $fh; }
    }

    # Purge expired sessions opportunistically
    if (opendir(my $dh, $sessdir)) {
        for (readdir $dh) {
            next unless /^[0-9a-f]{64}$/;
            my $f = "$sessdir/$_";
            if (open(my $fh, '<', $f)) {
                my $exp = <$fh>; close $fh; chomp($exp //= 0);
                unlink $f if time() >= $exp;
            }
        }
    }

    # Generate token from /dev/urandom (fall back to SHA of entropy mix)
    my $tok;
    if (open(my $rng, '<:raw', '/dev/urandom')) {
        read($rng, my $bytes, 32); close $rng;
        $tok = unpack('H*', $bytes);
    } else {
        $tok = sha256_hex(rand() . time() . $$ . rand());
    }

    open(my $fh, '>', "$sessdir/$tok") or die "Cannot create session: $!";
    print $fh time() + $SESSION_MAX_AGE, "\n";
    close $fh;
    $tok;
}

sub del_session {
    my $tok = shift or return;
    $tok =~ /^[0-9a-f]{64}$/ or return;
    unlink "$sessdir/$tok";
}

sub check_password {
    my $pw = shift;
    return 0 unless length($pw) && -f $passwdf;
    open(my $fh, '<', $passwdf) or return 0;
    my $stored = <$fh>; close $fh; chomp($stored //= '');
    return sha256_hex($pw) eq $stored;
}

sub redirect_js { '<script>location.href="' . $_[0] . '"</script>' }

sub login_page {
    my $msg      = shift // '';
    my $msg_html = $msg ? "<p class=\"msg\">$msg</p>" : '';
    return <<HTML;
<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pix &mdash; Login</title><style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#1a1a1a;color:#e0e0e0;
     display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{background:#242424;border:1px solid #383838;border-radius:6px;
     padding:2.4rem 2.8rem;width:min(100%,360px);text-align:center}
h1{font-weight:300;font-size:1.3rem;color:#888;letter-spacing:.15em;
   text-transform:uppercase;margin-bottom:1.8rem}
input[type=password]{width:100%;background:#111;border:1px solid #444;border-radius:4px;
   color:#e0e0e0;font-size:1rem;padding:.6rem .85rem;margin-bottom:1.1rem;outline:none}
input[type=password]:focus{border-color:#6ab}
button{width:100%;background:#336;border:1px solid #669;color:#cce;
       padding:.6rem;border-radius:4px;font-size:1rem;cursor:pointer}
button:hover{background:#447}
.msg{color:#f88;font-size:.85rem;margin-bottom:.9rem}
</style></head><body>
<div class="box">
  <h1>Pix Gallery</h1>
  $msg_html
  <form method="post" action="pix-auth.cgi">
    <input type="password" name="password" placeholder="Password"
           autofocus autocomplete="current-password">
    <button type="submit">Enter</button>
  </form>
</div>
</body></html>
HTML
}
