using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using System.IO;

namespace AITuber.Editor
{
    public static class PackageImporter
    {
        [MenuItem("AITuber/Reload Current Scene")]
        public static void ReloadCurrentScene()
        {
            AssetDatabase.Refresh();
            var scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
            EditorSceneManager.OpenScene(scene.path);
            Debug.Log("[PackageImporter] Scene reloaded: " + scene.path);
        }

        [MenuItem("AITuber/Check QuQu Prefab GUID")]
        public static void CheckQuQuPrefabGuid()
        {
            const string guid = "2a82daac7d2bbcc44bf68d9f3ee78bb3";
            string path = AssetDatabase.GUIDToAssetPath(guid);
            if (string.IsNullOrEmpty(path))
                Debug.LogError($"[QuQu] GUID {guid} NOT found in AssetDatabase!");
            else
                Debug.Log($"[QuQu] GUID found: {path}");

            // Also search for prefabs manually
            string[] prefabGuids = AssetDatabase.FindAssets("t:Prefab", new[] { "Assets/QuQu" });
            foreach (var pg in prefabGuids)
                Debug.Log($"[QuQu] Prefab in project: GUID={pg} Path={AssetDatabase.GUIDToAssetPath(pg)}");
        }

        [MenuItem("AITuber/Reinstantiate QuQu Under AvatarRoot")]
        public static void ReinstantiateQuQu()
        {
            // 1. Find AvatarRoot
            var avatarRootGO = GameObject.Find("AvatarRoot");
            if (avatarRootGO == null) { Debug.LogError("[QuQu] AvatarRoot not found!"); return; }

            // 2. Remove any existing children (Missing Prefab placeholder)
            for (int i = avatarRootGO.transform.childCount - 1; i >= 0; i--)
            {
                var child = avatarRootGO.transform.GetChild(i).gameObject;
                Debug.Log($"[QuQu] Removing child: {child.name}");
                Object.DestroyImmediate(child);
            }

            // 3. Load the QuQu prefab
            const string guid = "2a82daac7d2bbcc44bf68d9f3ee78bb3";
            string prefabPath = AssetDatabase.GUIDToAssetPath(guid);
            if (string.IsNullOrEmpty(prefabPath)) { Debug.LogError($"[QuQu] Prefab GUID {guid} not found!"); return; }

            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
            if (prefab == null) { Debug.LogError($"[QuQu] Failed to load prefab at {prefabPath}"); return; }

            // 4. Instantiate prefab as child of AvatarRoot
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab, avatarRootGO.transform);
            instance.transform.localPosition = Vector3.zero;
            instance.transform.localRotation = Quaternion.identity;
            instance.transform.localScale = Vector3.one;
            Debug.Log($"[QuQu] Instantiated: {instance.name} under AvatarRoot. InstanceID={instance.GetInstanceID()}");

            // 5. Wire up AvatarController fields (Animator and Face SMR)
            var avatarController = avatarRootGO.GetComponent<MonoBehaviour>();
            var allScripts = avatarRootGO.GetComponents<MonoBehaviour>();
            foreach (var mb in allScripts)
            {
                if (mb == null) continue;
                var t = mb.GetType();
                if (t.Name != "AvatarController") continue;

                // Find Animator in instance
                var animator = instance.GetComponentInChildren<Animator>(true);
                if (animator != null)
                {
                    var animField = t.GetField("_animator", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
                    animField?.SetValue(mb, animator);
                    Debug.Log($"[QuQu] Set _animator = {animator.gameObject.name}");
                }

                // Find the first SkinnedMeshRenderer (Body/Face mesh) in instance
                var smrs = instance.GetComponentsInChildren<SkinnedMeshRenderer>(true);
                SkinnedMeshRenderer faceSMR = null;
                foreach (var smr in smrs)
                {
                    if (smr.name.ToLower().Contains("body") || smr.name.ToLower().Contains("face") || faceSMR == null)
                        faceSMR = smr;
                    if (smr.name.ToLower().Contains("body")) break;
                }
                if (faceSMR != null)
                {
                    var smrField = t.GetField("_faceMesh", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
                    smrField?.SetValue(mb, faceSMR);
                    Debug.Log($"[QuQu] Set _faceMesh = {faceSMR.name} (mesh has {faceSMR.sharedMesh?.blendShapeCount} blendshapes)");
                }
                break;
            }

            // 6. Save the scene
            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(
                UnityEngine.SceneManagement.SceneManager.GetActiveScene());
            UnityEditor.SceneManagement.EditorSceneManager.SaveOpenScenes();
            Debug.Log("[QuQu] Scene saved!");
        }


        [MenuItem("AITuber/Dump Body BlendShapes")]
        public static void DumpBodyBlendShapes()
        {
            var allSMRs = Object.FindObjectsByType<SkinnedMeshRenderer>(FindObjectsSortMode.None);
            SkinnedMeshRenderer smr = null;
            foreach (var s in allSMRs)
                if (s.gameObject.name == "Body") { smr = s; break; }
            if (smr == null || smr.sharedMesh == null) { Debug.LogError("[QuQu] Body SMR not found!"); return; }
            var sb = new System.Text.StringBuilder();
            sb.AppendLine($"Body BlendShapes ({smr.sharedMesh.blendShapeCount} total):");
            for (int i = 0; i < smr.sharedMesh.blendShapeCount; i++)
                sb.AppendLine($"[{i}] {smr.sharedMesh.GetBlendShapeName(i)}");
            string outPath = "C:/Users/iijmi/st/aituber/AITuber/Logs/body_blendshapes.txt";
            System.IO.Directory.CreateDirectory("C:/Users/iijmi/st/aituber/AITuber/Logs");
            System.IO.File.WriteAllText(outPath, sb.ToString());
            Debug.Log($"[QuQu] BlendShape dump written to {outPath}\n" + sb.ToString().Substring(0, Mathf.Min(500, sb.Length)));
        }

        [MenuItem("AITuber/Fix QuQu Materials to URP")]
        public static void FixQuQuMaterialsToURP()
        {
            var urpLit = Shader.Find("Universal Render Pipeline/Lit");
            if (urpLit == null) { Debug.LogError("[QuQu] URP/Lit shader not found!"); return; }

            string[] matGuids = AssetDatabase.FindAssets("t:Material", new[] { "Assets/QuQu" });
            int count = 0;
            foreach (string guid in matGuids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
                if (mat == null) continue;

                // Read texture references via SerializedObject (works regardless of shader)
                var so = new SerializedObject(mat);
                Texture mainTex = FindTextureInSerialized(so, "_MainTex");
                if (mainTex == null) mainTex = FindTextureInSerialized(so, "_1st_ShadeMap");
                if (mainTex == null) mainTex = FindTextureInSerialized(so, "_ShadeTexture");
                Texture shadeTex = FindTextureInSerialized(so, "_1st_ShadeMap");
                if (shadeTex == mainTex) shadeTex = null;

                mat.shader = urpLit;

                if (mainTex != null)
                {
                    mat.SetTexture("_BaseMap", mainTex);
                    mat.SetTexture("_MainTex", mainTex);
                }
                mat.SetColor("_BaseColor", Color.white);
                mat.SetFloat("_Metallic", 0f);
                mat.SetFloat("_Smoothness", 0f);
                mat.SetFloat("_Surface", 0f);
                mat.SetFloat("_Blend", 0f);
                mat.SetFloat("_AlphaClip", 0f);
                mat.renderQueue = -1;

                EditorUtility.SetDirty(mat);
                count++;
                Debug.Log($"[QuQu] Fixed material: {mat.name} (mainTex={mainTex?.name ?? "none"})");
            }
            AssetDatabase.SaveAssets();
            Debug.Log($"[QuQu] Fixed {count} materials to URP/Lit.");
        }

        static Texture FindTextureInSerialized(SerializedObject so, string propName)
        {
            var texEnvs = so.FindProperty("m_SavedProperties.m_TexEnvs");
            if (texEnvs == null) return null;
            for (int i = 0; i < texEnvs.arraySize; i++)
            {
                var entry = texEnvs.GetArrayElementAtIndex(i);
                var key = entry.FindPropertyRelative("first");
                if (key != null && key.stringValue == propName)
                {
                    var texProp = entry.FindPropertyRelative("second.m_Texture");
                    if (texProp != null)
                        return texProp.objectReferenceValue as Texture;
                }
            }
            return null;
        }

        // ─────────────────────────────────────────────────────────────────
        // Fix QuQu Pivot (Edit-mode: shift VRM child so feet land at ground)
        // ─────────────────────────────────────────────────────────────────
        [MenuItem("AITuber/Fix QuQu Pivot (Edit Mode)")]
        public static void FixQuQuPivotEditMode()
        {
            var avatarRootGO = GameObject.Find("AvatarRoot");
            if (avatarRootGO == null) { Debug.LogError("[QuQu] AvatarRoot not found!"); return; }

            // ① AvatarRoot 自身を原点にリセット
            Undo.RecordObject(avatarRootGO.transform, "Fix QuQu Pivot");
            avatarRootGO.transform.localPosition = Vector3.zero;
            avatarRootGO.transform.localRotation = Quaternion.identity;
            Debug.Log("[QuQu] AvatarRoot reset to (0,0,0)");

            // ② AvatarRoot の直接の子（QuQu プレハブインスタンス）を取得
            if (avatarRootGO.transform.childCount == 0)
                { Debug.LogError("[QuQu] AvatarRoot has no children!"); return; }
            Transform ququChild = avatarRootGO.transform.GetChild(0);

            // ③ humanoid Animator を取得（AvatarRoot 自身の Animator を優先）
            var anim = avatarRootGO.GetComponent<UnityEngine.Animator>();
            if (anim == null || !anim.isHuman || anim.avatar == null)
                foreach (var a in avatarRootGO.GetComponentsInChildren<UnityEngine.Animator>(true))
                    if (a.isHuman && a.avatar != null) { anim = a; break; }
            if (anim == null) { Debug.LogError("[QuQu] No valid humanoid Animator found!"); return; }

            // ④ まず QuQu child を localY=0 に戻してからボーン位置を計測
            //    変更前に Undo 登録（Undo.RecordObject は変更前に呼ぶ）
            Undo.RecordObject(ququChild, "Fix QuQu Pivot");
            var lp = ququChild.localPosition;
            lp.y = 0f;
            ququChild.localPosition = lp;

            // ⑤ 足ボーンの world Y を計測
            var lf = anim.GetBoneTransform(HumanBodyBones.LeftFoot);
            var rf = anim.GetBoneTransform(HumanBodyBones.RightFoot);
            if (lf == null || rf == null) { Debug.LogError("[QuQu] Foot bones not found!"); return; }

            const float footHeight = 0.05f;
            float ankleWorldY = (lf.position.y + rf.position.y) * 0.5f;
            float soleWorldY  = ankleWorldY - footHeight;

            // ⑥ sole が world y=0 になるよう QuQu child の localY を設定
            //    AvatarRoot が origin(0,0,0) なので: QuQu世界Y = localY、
            //    sole世界Y = soleWorldY + newLocalY = 0 → newLocalY = -soleWorldY
            lp.y = -soleWorldY;
            ququChild.localPosition = lp;

            // プレハブインスタンスのオーバーライドとして登録（Saveに反映させる）
            PrefabUtility.RecordPrefabInstancePropertyModifications(ququChild);

            Debug.Log($"[QuQu] Pivot fixed: {ququChild.name}.localY 0 → {lp.y:F4}  " +
                      $"(ankleWorld={ankleWorldY:F4}, soleWorld={soleWorldY:F4})");

            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(
                UnityEngine.SceneManagement.SceneManager.GetActiveScene());
            UnityEditor.SceneManagement.EditorSceneManager.SaveOpenScenes();
            Debug.Log($"[QuQu] Scene saved. {ququChild.name}.localY = {ququChild.localPosition.y:F4}");
        }

        [MenuItem("AITuber/Fix AvatarRoot Animator")]
        public static void FixAvatarRootAnimator()
        {
            var avatarRootGO = GameObject.Find("AvatarRoot");
            if (avatarRootGO == null) { Debug.LogError("[QuQu] AvatarRoot not found!"); return; }

            var animator = avatarRootGO.GetComponent<Animator>();
            if (animator == null) { Debug.LogError("[QuQu] No Animator on AvatarRoot!"); return; }

            // Load Avatar from FBX sub-assets
            string fbxPath = "Assets/QuQu/U/U.fbx";
            var allAssets = AssetDatabase.LoadAllAssetsAtPath(fbxPath);
            UnityEngine.Avatar fbxAvatar = null;
            foreach (var asset in allAssets)
            {
                if (asset is UnityEngine.Avatar av)
                {
                    fbxAvatar = av;
                    Debug.Log($"[QuQu] Found Avatar: {av.name} (isHuman={av.isHuman}, isValid={av.isValid})");
                    break;
                }
            }
            if (fbxAvatar == null) { Debug.LogError("[QuQu] No Avatar found in " + fbxPath); return; }

            // Load AnimatorController
            string ctrlPath = AssetDatabase.GUIDToAssetPath("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6");
            var controller = AssetDatabase.LoadAssetAtPath<RuntimeAnimatorController>(ctrlPath);
            if (controller == null) Debug.LogWarning("[QuQu] AnimatorController not found at " + ctrlPath);

            animator.avatar = fbxAvatar;
            if (controller != null) animator.runtimeAnimatorController = controller;

            Debug.Log($"[QuQu] AvatarRoot Animator set: avatar={fbxAvatar.name}, controller={controller?.name ?? "none"}");

            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(
                UnityEngine.SceneManagement.SceneManager.GetActiveScene());
            UnityEditor.SceneManagement.EditorSceneManager.SaveOpenScenes();
            Debug.Log("[QuQu] Scene saved.");
        }

        [MenuItem("AITuber/Remove Missing Scripts from QuQu")]
        public static void RemoveMissingScriptsFromQuQu()
        {
            // Find all GameObjects in scene that belong to QuQu
            var allGOs = Object.FindObjectsByType<Transform>(FindObjectsSortMode.None);
            int removed = 0;
            foreach (var t in allGOs)
            {
                int count = GameObjectUtility.RemoveMonoBehavioursWithMissingScript(t.gameObject);
                if (count > 0)
                {
                    Debug.Log($"[QuQu] Removed {count} missing scripts from {t.name}");
                    removed += count;
                }
            }
            // Also process the prefab asset
            string prefabPath = AssetDatabase.GUIDToAssetPath("2a82daac7d2bbcc44bf68d9f3ee78bb3");
            if (!string.IsNullOrEmpty(prefabPath))
            {
                var prefabGO = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
                if (prefabGO != null)
                {
                    var prefabTransforms = prefabGO.GetComponentsInChildren<Transform>(true);
                    foreach (var pt in prefabTransforms)
                    {
                        int c = GameObjectUtility.RemoveMonoBehavioursWithMissingScript(pt.gameObject);
                        if (c > 0)
                        {
                            removed += c;
                            Debug.Log($"[QuQu] Removed {c} missing scripts from prefab/{pt.name}");
                        }
                    }
                    PrefabUtility.SavePrefabAsset(prefabGO);
                }
            }
            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(
                UnityEngine.SceneManagement.SceneManager.GetActiveScene());
            UnityEditor.SceneManagement.EditorSceneManager.SaveOpenScenes();
            Debug.Log($"[QuQu] Total missing scripts removed: {removed}");
        }
    }
}
