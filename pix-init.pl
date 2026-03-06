#!/usr/bin/perl
#
# pix-init.pl — Photo gallery initialization
#
# Usage:  perl pix-init.pl [/path/to/gallery]
#
# Scans a directory tree for photos, generates thumbnail / medium / large
# JPEG versions with ImageMagick, and writes _pix/index.json for the
# JavaScript gallery viewer.  Safe to re-run; skips files that are already
# up to date (output mtime >= input mtime).
#
# Also called by pix-init.cgi when initialization is triggered from a browser.
#
use strict;
use warnings;
use File::Basename  qw(basename dirname);
use File::Path      qw(make_path);
use Cwd             qw(abs_path);
use JSON::PP;
use POSIX           qw(strftime);

# ── Configuration ─────────────────────────────────────────────────────────────

my $PIX_DIR   = '_pix';
my @SIZE_ORDER = qw(thumb medium large);
my %SIZE      = (thumb => 150,  medium => 800,  large => 1600);
my %QUALITY   = (thumb => 80,   medium => 85,   large =>   90);
my %IMG_EXT   = map { $_ => 1 } qw(jpg jpeg png webp gif);

# ── Helpers ───────────────────────────────────────────────────────────────────

my $log_fh;   # set in main(); used for progress output

sub log_msg {
    my $msg = shift;
    print "$msg\n";
    STDOUT->flush();
    if ($log_fh) { print $log_fh "$msg\n"; $log_fh->flush(); }
}

sub is_image {
    my ($ext) = $_[0] =~ /\.([^.]+)$/;
    return defined($ext) && $IMG_EXT{ lc($ext) };
}

# Convert a source-relative path to the output .jpg path under a size dir.
# e.g. thumb_path('thumb', 'vacation/beach.png') -> '_pix/thumb/vacation/beach.jpg'
sub thumb_path {
    my ($sz, $rel) = @_;
    (my $out = $rel) =~ s/\.[^.]+$/.jpg/;
    return "$PIX_DIR/$sz/$out";
}

sub get_dimensions {
    my $file = shift;
    open(my $fh, '-|', 'identify', '-format', '%[fx:w] %[fx:h]', $file)
        or return (0, 0);
    my $line = <$fh>;
    close $fh;
    return (0, 0) unless $line;
    my ($w, $h) = split /\s+/, $line, 2;
    return (int($w // 0), int($h // 0));
}

sub generate_sizes {
    my ($root, $rel) = @_;
    my $src        = "$root/$rel";
    my $src_mtime  = (stat $src)[9];

    for my $sz (@SIZE_ORDER) {
        my $out_rel = thumb_path($sz, $rel);
        my $out     = "$root/$out_rel";
        make_path(dirname($out)) unless -d dirname($out);

        if (-f $out && (stat $out)[9] >= $src_mtime) { next; }  # already current

        my @cmd = ('convert', $src,
            '-auto-orient', '-strip',
            '-resize', "$SIZE{$sz}x$SIZE{$sz}>",
            '-quality', $QUALITY{$sz},
            $out);
        my $rc = system(@cmd);
        log_msg("  WARNING: convert failed for $rel ($sz)")  if $rc;
    }
}

# ── Directory scanner ─────────────────────────────────────────────────────────

sub scan_dir {
    my ($root, $rel) = @_;
    my $abs = $rel ? "$root/$rel" : $root;

    opendir(my $dh, $abs) or do {
        log_msg("WARNING: cannot open $abs: $!");
        return undef;
    };
    my @entries = sort grep { !/^\./ && $_ ne $PIX_DIR } readdir($dh);
    closedir($dh);

    my (@photos, @subdirs);

    for my $e (@entries) {
        my $rel_e = $rel ? "$rel/$e" : $e;
        if    (-d "$abs/$e")                    { my $sub = scan_dir($root, $rel_e); push @subdirs, $sub if $sub; }
        elsif (-f "$abs/$e" && is_image($e))    {
            log_msg("  $rel_e");
            generate_sizes($root, $rel_e);
            my ($w, $h) = get_dimensions("$abs/$e");
            push @photos, {
                name  => $e,
                path  => $rel_e,
                w     => $w + 0,
                h     => $h + 0,
                bytes => (stat "$abs/$e")[7] + 0,
                mtime => (stat "$abs/$e")[9] + 0,
            };
        }
    }

    # Cover image: first photo in this subtree (for directory card preview)
    my $cover;
    if (@photos) {
        $cover = thumb_path('medium', $photos[0]{path});
    } else {
        for my $sub (@subdirs) { if ($sub->{cover}) { $cover = $sub->{cover}; last; } }
    }

    return {
        name   => $rel ? basename($rel) : basename($root),
        path   => $rel // '',
        cover  => $cover,
        dirs   => \@subdirs,
        photos => \@photos,
    };
}

# ── Main ──────────────────────────────────────────────────────────────────────

sub main {
    my $dir = @_ ? shift : '.';
    $dir = abs_path($dir);
    die "Directory not found: $dir\n" unless -d $dir;

    my $pix_dir = "$dir/$PIX_DIR";
    make_path($pix_dir);
    open($log_fh, '>', "$pix_dir/log.txt") or undef $log_fh;

    log_msg("pix-init: $dir");
    log_msg("");

    for my $sz (@SIZE_ORDER) { make_path("$pix_dir/$sz"); }

    my $tree = scan_dir($dir, undef);

    my $index = {
        version   => 1,
        generated => strftime("%Y-%m-%dT%H:%M:%S", localtime),
        tree      => $tree,
    };

    my $json_path = "$pix_dir/index.json";
    open(my $jfh, '>', $json_path) or die "Cannot write $json_path: $!\n";
    print $jfh JSON::PP->new->utf8->pretty(1)->canonical(1)->encode($index);
    close $jfh;

    # Remove the running sentinel if it exists (placed by pix-init.cgi)
    unlink "$pix_dir/.running";

    log_msg("");
    log_msg("Done.  Index: $json_path");
    close $log_fh if $log_fh;
}

main(@ARGV) unless caller;
1;
