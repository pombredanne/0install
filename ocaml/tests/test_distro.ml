(* Copyright (C) 2013, Thomas Leonard
 * See the README file for details, or visit http://0install.net.
 *)

open Zeroinstall.General
open Support.Common
open OUnit
module Q = Support.Qdom
open Fake_system
module Distro = Zeroinstall.Distro
module F = Zeroinstall.Feed
module U = Support.Utils

let test_feed = "<?xml version='1.0'?>\n\
<interface xmlns='http://zero-install.sourceforge.net/2004/injector/interface' uri='http://repo.roscidus.com/python/python'>\n\
  <name>Test</name>\n\
\n\
  <package-implementation distributions='Cygwin' main='/usr/bin/python' package='python'/>\n\
\n\
  <package-implementation distributions='RPM' main='/usr/bin/python' package='python'/>\n\
  <package-implementation distributions='RPM' main='/usr/bin/python3' package='python3'/>\n\
  <package-implementation distributions='Gentoo' main='/usr/bin/python' package='dev-lang/python'/>\n\
\n\
  <package-implementation distributions='Debian' main='/usr/bin/python2.7' package='python2.7'/>\n\
  <package-implementation distributions='Debian' main='/usr/bin/python3' package='python3'/>\n\
\n\
  <package-implementation distributions='Arch' main='/usr/bin/python2' package='python2'/>\n\
  <package-implementation distributions='Arch' main='/usr/bin/python3' package='python'/>\n\
\n\
  <package-implementation distributions='Ports' main='/usr/local/bin/python2.6' package='python26'/>\n\
\n\
  <package-implementation distributions='MacPorts' main='/opt/local/bin/python2.7' package='python27'/>\n\
</interface>"

let test_gobject_feed = "<?xml version='1.0'?>\n\
<interface xmlns='http://zero-install.sourceforge.net/2004/injector/interface' uri='http://repo.roscidus.com/python/python-gobject'>\n\
  <name>gobject</name>\n\
  <package-implementation package='python-idontexist'/>\n\
</interface>"

let load_feed system xml =
    let root = Q.parse_input None @@ Xmlm.make_input (`String (0, xml)) in
    F.parse system root None

let get_test_slave config name args =
  let slave = new Zeroinstall.Python.slave config in
  slave#invoke (`List [`String "test-distro"; `String name; `List args]) Zeroinstall.Python.expect_null;
  slave

let suite = "distro">::: [
  "arch">:: Fake_system.with_tmpdir (fun tmpdir ->
    skip_if (Sys.os_type = "Win32") "Paths get messed up on Windows";

    let (config, fake_system) = Fake_system.get_fake_config (Some tmpdir) in
    fake_system#add_file "/var/lib/pacman/local/python2-2.7.2-4/desc" "../../tests/arch/local/python2-2.7.2-4/desc";
    fake_system#hide_path "/usr/bin/python2";
    fake_system#hide_path "/usr/bin/python3";
    assert (not @@ fake_system#file_exists "/usr/bin/python2");
    fake_system#add_dir "/bin" ["python2"; "python3"];
    let system = (fake_system :> system) in
    let slave = new Zeroinstall.Python.slave config in
    let distro = new Distro.ArchLinux.arch_distribution config slave in
    let feed = load_feed system test_feed in
    let impls = Distro.get_package_impls distro feed in
    let open F in
    match impls with
    | Some [impl] ->
        assert_str_equal "2.7.2-4" (Zeroinstall.Versions.format_version impl.parsed_version);
        let run = StringMap.find "run" impl.props.commands in
        assert_str_equal "/bin/python2" (ZI.get_attribute "path" run.command_qdom)
    | Some impls -> assert_failure @@ Printf.sprintf "want 1 Python, got %d" (List.length impls)
    | None -> assert_failure "didn't check distro!"
  );

  "test_host_python">:: Fake_system.with_tmpdir (fun tmpdir ->
    let (config, fake_system) = Fake_system.get_fake_config (Some tmpdir) in
    let system = (fake_system :> system) in

    let python_path = Support.Utils.find_in_path_ex Fake_system.real_system "python" in
    fake_system#add_file python_path python_path;

    let my_spawn_handler args cin cout cerr =
      Fake_system.real_system#create_process args cin cout cerr in
    fake_system#set_spawn_handler (Some my_spawn_handler);

    let slave = new Zeroinstall.Python.slave config in
    let distro = new Distro.generic_distribution slave in

    let open F in
    let is_host impl = U.starts_with (get_attr_ex "id" impl) "package:host:" in
    let find_host impls =
      try List.find is_host impls
      with Not_found -> assert_failure "No host package found!" in

    let root = Q.parse_input None @@ Xmlm.make_input (`String (0, test_feed)) in
    let feed = parse system root None in
    let () =
      match Distro.get_package_impls distro feed with
      | None -> assert_failure "Didn't check!"
      | Some impls ->
          let host_python = find_host impls in
          let python_run =
            try StringMap.find "run" host_python.props.commands
            with Not_found -> assert_failure "No run command for host Python" in
          assert (Fake_system.real_system#file_exists (ZI.get_attribute "path" python_run.command_qdom)) in

    (* python-gobject *)
    let root = Q.parse_input None @@ Xmlm.make_input (`String (0, test_gobject_feed)) in
    let feed = F.parse system root None in
    let () =
      match Distro.get_package_impls distro feed with
      | None -> assert_failure "Didn't check!"
      | Some impls ->
          let host_gobject = find_host impls in
          let () =
            match host_gobject.props.requires with
            | [ {dep_importance = Dep_restricts; dep_iface = "http://repo.roscidus.com/python/python"; dep_restrictions = [_]; _ } ] -> ()
            | _ -> assert_failure "No host restriction for host python-gobject" in
          let sel = ZI.make host_gobject.qdom.Q.doc "selection" in
          sel.Q.attrs <- AttrMap.bindings host_gobject.props.attrs;
          Q.set_attribute "from-feed" (Zeroinstall.Feed_url.format_url (`distribution_feed feed.url)) sel;
          assert (Distro.is_installed config distro sel) in
    slave#close;
  );

  "rpm">:: Fake_system.with_fake_config (fun (config, _fake_system) ->
    let rpmdir = Test_0install.feed_dir +/ "rpm" in
    let old_path = Unix.getenv "PATH" in
    Unix.putenv "PATH" (rpmdir ^ ":" ^ old_path);

    let slave = get_test_slave config "RPMDistribution" [`String (rpmdir +/ "status")] in
    let rpm = new Distro.RPM.rpm_distribution config slave in

    let get_feed xml = load_feed config.system (Printf.sprintf
      "<?xml version='1.0'?>\n\
      <interface xmlns='http://zero-install.sourceforge.net/2004/injector/interface' uri='http://example.com/yast2-update'>\n\
        <name>yast2</name>\n%s\n\
      </interface>" xml) in

    let feed = get_feed
      "<package-implementation distributions='Debian' package='yast2-mail'/>\n\
       <package-implementation distributions='RPM' package='yast2-update'/>" in
    let impls = Fake_system.expect @@ Distro.get_package_impls rpm feed in
    begin match impls with
    | [yast] ->
        assert_equal "package:rpm:yast2-update:2.15.23-21:i586" (F.get_attr_ex "id" yast);
        assert_equal "2.15.23-21" (F.get_attr_ex "version" yast);
        assert_equal "*-i586" (Zeroinstall.Arch.format_arch yast.F.os yast.F.machine);
    | _ -> assert false end;

    let feed = get_feed "<package-implementation distributions='RPM' package='yast2-mail'/>\n\
                         <package-implementation distributions='RPM' package='yast2-update'/>" in
    let impls = Fake_system.expect @@ Distro.get_package_impls rpm feed in
    assert_equal 2 (List.length impls);

    let feed = get_feed "<package-implementation distributions='' package='yast2-mail'/>\n\
                         <package-implementation package='yast2-update'/>" in
    let impls = Fake_system.expect @@ Distro.get_package_impls rpm feed in
    assert_equal 2 (List.length impls);

    let feed = get_feed "<package-implementation distributions='Foo Bar Baz' package='yast2-mail'/>" in
    let impls = Fake_system.expect @@ Distro.get_package_impls rpm feed in
    assert_equal 1 (List.length impls);

    Unix.putenv "PATH" old_path;
  );

  "debian">:: Fake_system.with_fake_config (fun (config, _fake_system) ->
    let xml =
      "<?xml version='1.0' ?>\n\
      <interface xmlns='http://zero-install.sourceforge.net/2004/injector/interface'>\n\
      <name>Foo</name>\n\
      <summary>Foo</summary>\n\
      <description>Foo</description>\n\
      <package-implementation package='gimp'/>\n\
      <package-implementation package='python-bittorrent' foo='bar' main='/usr/bin/pbt'/>\n\
      </interface>" in
    let root = `String (0, xml) |> Xmlm.make_input |> Q.parse_input None in

    let _url = "http://foo" in
    let feed = F.parse config.system root (Some "/local.xml") in

    assert_equal 0 (StringMap.cardinal feed.F.implementations);

    let dpkgdir = Test_0install.feed_dir +/ "dpkg" in
    let old_path = Unix.getenv "PATH" in
    Unix.putenv "PATH" (dpkgdir ^ ":" ^ old_path);
    let slave = get_test_slave config "DebianDistribution" [`String (dpkgdir +/ "status")] in
    let deb = new Distro.Debian.debian_distribution config slave in
    begin match Fake_system.expect @@ Distro.get_package_impls deb feed with
    | [impl] ->
        Fake_system.assert_str_equal "package:deb:python-bittorrent:3.4.2-10:*" (F.get_attr_ex "id" impl);
        assert_equal ~msg:"Stability" Packaged impl.F.stability;
        assert_equal ~msg:"Requires" [] impl.F.props.F.requires;
        Fake_system.assert_str_equal "/usr/bin/pbt" (ZI.get_attribute_opt "main" impl.F.qdom |> Fake_system.expect);
        assert_equal (Some "bar") @@ Q.get_attribute_opt ("", "foo") impl.F.qdom;
        Fake_system.assert_str_equal "distribution:/local.xml" (F.get_attr_ex "from-feed" impl);
    | _ -> assert false end;

    let get_feed xml = load_feed config.system (Printf.sprintf
      "<?xml version='1.0'?>\n\
      <interface xmlns='http://zero-install.sourceforge.net/2004/injector/interface' uri='http://example.com/bittorrent'>\n\
        <name>dummy</name>\n%s\n\
      </interface>" xml) in

    (* testCommand *)
    let feed = get_feed "<package-implementation main='/unused' package='python-bittorrent'><command path='/bin/sh' name='run'/></package-implementation>" in
    let requirements = Zeroinstall.Requirements.default_requirements "http://example.com/bittorrent" in
    let feed_provider =
      object
        inherit Zeroinstall.Feed_provider.feed_provider config deb
        method! get_feed = function
          | (`remote_feed "http://example.com/bittorrent") as url ->
              let result = Some (feed, F.({ last_checked = None; user_stability = StringMap.empty })) in
              cache <- Zeroinstall.Feed_provider.FeedMap.add url result cache;
              result
          | _ -> assert false
      end in
    begin match Zeroinstall.Solver.solve_for config feed_provider requirements with
    | (true, results) ->
        let sels = results#get_selections |> Zeroinstall.Selections.make_selection_map in
        let sel = StringMap.find "http://example.com/bittorrent" sels in
        let run = Zeroinstall.Command.get_command_ex "run" sel in
        Fake_system.assert_str_equal "/bin/sh" (ZI.get_attribute "path" run)
    | _ -> assert false end;
    Fake_system.fake_log#reset;

    (* Part II *)
    let gimp_feed = get_feed "<package-implementation package='gimp'/>" in
    Distro.get_package_impls deb gimp_feed |> assert_equal (Some []);

    (* Initially, we only get information about the installed version... *)
    let bt_feed = get_feed "<package-implementation package='python-bittorrent'>\n\
                                <restricts interface='http://python.org/python'>\n\
                                  <version not-before='3'/>\n\
                                </restricts>\n\
                                </package-implementation>" in
    Distro.get_package_impls deb bt_feed |> Fake_system.expect |> List.length |> assert_equal 1;


    Fake_system.fake_log#reset;

    (* Tell distro to fetch information about candidates... *)
    Lwt_main.run (deb#check_for_candidates bt_feed);

    (* Now we see the uninstalled package *)
    let compare_version a b = compare a.F.parsed_version b.F.parsed_version in
    begin match Fake_system.expect @@ Distro.get_package_impls deb bt_feed |> List.sort compare_version with
    | [installed; uninstalled] as impls ->
        (* Check restriction appears for both candidates *)
        impls |> List.iter (fun impl ->
          match impl.F.props.F.requires with
          | [{F.dep_iface = "http://python.org/python"; _}] -> ()
          | _ -> assert false
        );
        Fake_system.assert_str_equal "3.4.2-10" (F.get_attr_ex "version" installed);
        assert_equal true @@ F.is_available_locally config installed;
        assert_equal false @@ F.is_available_locally config uninstalled;
        assert_equal None installed.F.machine;
    | _ -> assert false
    end;

    let feed = get_feed "<package-implementation package='libxcomposite-dev'/>" in
    begin match Distro.get_package_impls deb feed with
    | Some [libxcomposite] ->
        Fake_system.assert_str_equal "0.3.1-1" @@ F.get_attr_ex "version" libxcomposite;
        Fake_system.assert_str_equal "i386" @@ Fake_system.expect libxcomposite.F.machine
    | _ -> assert false
    end;

    (* Java is special... *)
    let feed = get_feed "<package-implementation package='openjdk-7-jre'/>" in
    begin match Distro.get_package_impls deb feed with
    | Some [impl] -> Fake_system.assert_str_equal "7.3-2.1.1-3" @@ F.get_attr_ex "version" impl
    | _ -> assert false end;

    Unix.putenv "PATH" old_path;
  );
]
