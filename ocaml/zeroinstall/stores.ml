(* Copyright (C) 2013, Thomas Leonard
 * See the README file for details, or visit http://0install.net.
 *)

(** Managing cached implementations *)

open General
open Support.Common
module U = Support.Utils

type stores = string list

type digest = (string * string)

type available_digests = (string, filepath) Hashtbl.t

exception Not_stored of string

let first_match = Support.Utils.first_match

let format_digest (alg, value) =
  let s = match alg with
  | "sha1" | "sha1new" | "sha256" -> alg ^ "=" ^ value
  | _ -> alg ^ "_" ^ value in
  (* validate *)
  s

let lookup_digest (system:system) stores digest =
  let check_store store = (
    let path = Filename.concat store (format_digest digest) in
    if system#file_exists path then Some path else None
  ) in first_match ~f:check_store stores

let lookup_maybe system digests stores = first_match ~f:(lookup_digest system stores) digests

let lookup_any system digests stores =
  match lookup_maybe system digests stores with
  | Some path -> path
  | None ->
      let str_digests = String.concat ", " (List.map format_digest digests) in
      let str_stores = String.concat ", " stores in
      raise (Not_stored ("Item with digests " ^ str_digests ^ " not found in stores. Searched " ^ str_stores))

let get_default_stores basedir_config =
  let open Support.Basedir in
  List.map (fun prefix -> prefix +/ "0install.net" +/ "implementations") basedir_config.cache

let get_available_digests (system:system) stores =
  let digests = Hashtbl.create 1000 in
  let scan_dir dir =
    match system#readdir dir with
    | Success items ->
        for i = 0 to Array.length items - 1 do
          Hashtbl.add digests items.(i) dir
        done
    | Problem _ -> log_debug "Can't scan %s" dir
    in
  List.iter scan_dir stores;
  digests

let check_available available_digests digests =
  List.exists (fun d -> Hashtbl.mem available_digests (format_digest d)) digests

let get_digests elem =
  let id = ZI.get_attribute "id" elem in
  let init = match Str.bounded_split_delim U.re_equals id 2 with
  | [key; value] when key = "sha1" || key = "sha1new" || key = "sha256" -> [(key, value)]
  | _ -> [] in

  let check_attr init ((ns, name), value) = match ns with
    | "" -> (name, value) :: init
    | _ -> init in
  let extract_digests init elem =
    List.fold_left check_attr init elem.Support.Qdom.attrs in
  ZI.fold_left ~f:extract_digests init elem "manifest-digest"

(* Preferred algorithms score higher. None if we don't support this algorithm at all. *)
let score_alg = function
  | "sha256new" -> Some 90
  | "sha256"    -> Some 80
  | "sha1new"   -> Some 50
  | "sha1"      -> Some 10
  | _ -> None

let best_digest digests =
  let best = ref None in
  digests |> List.iter (fun digest ->
    match score_alg (fst digest) with
    | None -> ()
    | Some score ->
        match !best with
        | Some (old_score, _) when old_score >= score -> ()
        | _ -> best := Some (score, digest)
  );
  match !best with
  | Some (_score, best) -> best
  | None ->
      let algs = digests |> List.map fst |> String.concat ", " in
      raise_safe "None of the candidate digest algorithms (%s) is supported" algs

let make_tmp_dir (system:system) = function
  | store :: _ ->
      U.makedirs system store 0o755;
      let mode = 0o755 in     (* r-x for all; needed by 0store-helper *)
      U.make_tmp_dir system ~mode store
  | _ -> raise_safe "No stores configured!"
