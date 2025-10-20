using Avalonia;
using Avalonia.Controls;
using Avalonia.Media;
using Avalonia.Platform;
using Avalonia.Rendering.SceneGraph;
using Avalonia.Skia;
using SkiaSharp;
using System;
using System.Collections.Generic;
using System.Linq;

namespace My_class
{
    /// <summary>
    /// Skia圖表基礎抽象類 - 提供圖表繪製的基本功能
    /// 繼承自 Avalonia 的 Control 類，支援自定義繪製
    /// </summary>
    public abstract class SkiaChart_Base : Control
    {
        #region 各項參數的初始化

        /// 數據鎖 - 用於保護多執行緒環境下的數據存取安全
        private readonly object _dataLock = new object();
        /// 圖表數據點列表 - 存儲要繪製的浮點數數據
        private readonly List<float> 繪製資料_List = new List<float>();
        /// 渲染實例ID生成器 - 用於識別不同的渲染操作
        private readonly Random Rd_繪圖底層ID隔絕 = new Random();

        // === 新增：SKPath 快取相關 ===
        /// 快取的繪製路徑，避免每次重新計算點位置
        private SKPath _cachedPath = new SKPath();
        /// 標記路徑是否需要更新
        private bool _pathNeedsUpdate = true;
        /// 記錄上次計算時的畫布尺寸，用來偵測尺寸變化
        private float _lastCanvasWidth = 0;
        private float _lastCanvasHeight = 0;
        /// 記錄上次的資料範圍，用來偵測縮放變化
        private float _lastMinY = 0;
        private float _lastMaxY = 0;
        /// 資料變化的標記
        private bool _dataChanged = true;

        // 畫布基本設定
        private readonly SKPaint SKP_線條屬性;
        private readonly SKPaint SKP_背景屬性;
        private readonly SKPaint SKP_Y軸刻度;
        private readonly SKPaint SKP_XY軸的刻度文字;

        private int 資料量 = 2000;
        protected abstract SKColor 線條顏色 { get; }
        protected virtual float 線條寬度 => 3f;
        protected virtual string 圖表標題 => "";

        protected SkiaChart_Base()
        {
            SKP_線條屬性 = new SKPaint
            {
                Color = 線條顏色,
                IsAntialias = true,
                StrokeWidth = 線條寬度,
                Style = SKPaintStyle.Stroke,
                StrokeCap = SKStrokeCap.Round,
                StrokeJoin = SKStrokeJoin.Round
            };

            SKP_背景屬性 = new SKPaint
            {
                Color = SKColors.Black, //白色背景
                Style = SKPaintStyle.Fill,
                IsAntialias = false
            };

            SKP_Y軸刻度 = new SKPaint
            {
                Color = SKColors.Gray, //設定灰色
                IsAntialias = true, // 平滑抗鋸齒
                StrokeWidth = 2.4f, // 2.4像素
                Style = SKPaintStyle.Stroke // 方形框框（透明中心），看起來像「框線」
            };

            SKP_XY軸的刻度文字 = new SKPaint
            {
                Color = SKColors.White, // 顯示字為黑色
                IsAntialias = true, // 抗鋸齒，避免小字看起來破破的
                TextSize = 13, // 刻度的字體大小
                Style = SKPaintStyle.Fill
            };
        }

        /// <summary>
        /// 物件銷毀時釋放 SKPath 資源
        /// </summary>
        protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e)
        {
            base.OnDetachedFromVisualTree(e);
            _cachedPath?.Dispose();
        }

        #endregion

        #region 數據操作

        /// <summary>
        /// 添加新的數據點到圖表中
        /// 自動限制數據點數量，超過500個時會移除最舊的數據
        /// 使用執行緒安全的方式更新數據並觸發重繪
        /// </summary>
        /// <param name="value">要添加的數據點值</param>
        public void 添加數據點(float value)
        {
            // 使用鎖確保執行緒安全 保證每一條線一次只能被更新一次數據
            lock (_dataLock)
            {
                繪製資料_List.Add(value);
                // 限制數據點數量，避免記憶體過度使用
                if (繪製資料_List.Count >= 資料量)
                {  // 減少數據點限制
                    int 超出數 = 繪製資料_List.Count - 資料量;
                    繪製資料_List.RemoveRange(0, 超出數);
                }
                // === 新增：標記資料已變化，需要重新計算路徑 ===
                _dataChanged = true;
                _pathNeedsUpdate = true;
            }
            // 考慮到可能資料更新太快會造成 UI 堵塞所以資料跟新時不更新UI
        }

        /// <summary>
        /// 添加多筆數據點到圖表中
        /// 自動限制數據點數量，超過限制時移除最舊的資料
        /// 使用執行緒安全的方式更新資料並觸發重繪標記
        /// </summary>
        /// <param name="values">要加入的多筆資料</param>
        public void 添加多筆數據點(List<float> values)
        {
            if (values == null || values.Count == 0)
                return;

            lock (_dataLock)
            {
                繪製資料_List.AddRange(values);

                // 超出資料量上限則移除最舊的資料
                int 超出數 = 繪製資料_List.Count - 資料量;
                if (超出數 > 0)
                    繪製資料_List.RemoveRange(0, 超出數);

                _dataChanged = true;
                _pathNeedsUpdate = true;
            }
            // 同樣不直接呼叫 InvalidateVisual()，由外部自行控制是否重畫
        }

        /// <summary>
        /// 考慮到說可能使用者要自己設置中斷跟新，所以建立函數處理UI的跟新
        /// </summary>
        public void 重畫畫布()
        {
            // 使用低優先級調度避免UI阻塞
            Avalonia.Threading.Dispatcher.UIThread.Post(() =>
            {
                InvalidateVisual();   // 標記控件需要重繪
            }, Avalonia.Threading.DispatcherPriority.Background);
        }

        /// <summary>
        /// 清空所有數據點並觸發重繪
        /// 執行緒安全的清除操作
        /// </summary>
        public void 清空數據()
        {
            lock (_dataLock)
            {
                繪製資料_List.Clear();
                // === 新增：清空資料時也要重置路徑 ===
                _cachedPath.Dispose();
                _cachedPath = new SKPath();
                _dataChanged = true;
                _pathNeedsUpdate = true;
            }
            InvalidateVisual();  // 立即觸發重繪
        }

        /// <summary>
        /// 新增：更新 SKPath 快取的方法
        /// 只有在資料或畫布尺寸改變時才會重新計算，大幅提升效能
        /// </summary>
        /// <param name="canvasWidth">畫布寬度</param>
        /// <param name="canvasHeight">畫布高度</param>
        /// <param name="dataList">資料點列表</param>
        private void 更新路徑快取(float canvasWidth, float canvasHeight, List<float> dataList)
        {
            // 檢查是否需要更新路徑
            bool 尺寸已改變 = Math.Abs(_lastCanvasWidth - canvasWidth) > 0.1f ||
                           Math.Abs(_lastCanvasHeight - canvasHeight) > 0.1f;

            if (!_pathNeedsUpdate && !尺寸已改變 && !_dataChanged)
                return; // 沒有變化就不需要重新計算

            if (dataList.Count < 2)
            {
                _cachedPath.Reset();
                return;
            }

            // 計算資料範圍
            float maxY = dataList.Max();
            float minY = dataList.Min();
            if (maxY <= minY) maxY = minY + 100f;

            // 檢查資料範圍是否改變
            bool 範圍已改變 = Math.Abs(_lastMinY - minY) > 0.001f ||
                           Math.Abs(_lastMaxY - maxY) > 0.001f;

            if (!_pathNeedsUpdate && !尺寸已改變 && !_dataChanged && !範圍已改變)
                return;

            // 重新建立路徑
            _cachedPath.Reset();

            float 左間距 = 46f + 3f; // 對應原本的 DO_左間距 + 3
            float 波形圖寬 = canvasWidth - 左間距;
            float stepX = dataList.Count > 1 ? 波形圖寬 / (dataList.Count - 1) : 0;

            // 第一個點
            float normalizedY = (maxY == minY) ? 0.5f : (dataList[0] - minY) / (maxY - minY);
            float startY = canvasHeight - (normalizedY * canvasHeight);
            startY = Math.Max(0, Math.Min(canvasHeight, startY));

            _cachedPath.MoveTo(左間距, startY);

            // 後續的點
            for (int i = 1; i < dataList.Count; i++)
            {
                float x = 左間距 + (i * stepX);
                normalizedY = (maxY == minY) ? 0.5f : (dataList[i] - minY) / (maxY - minY);
                float y = canvasHeight - (normalizedY * canvasHeight);

                x = Math.Max(左間距, Math.Min(canvasWidth, x));
                y = Math.Max(0, Math.Min(canvasHeight, y));

                _cachedPath.LineTo(x, y);
            }

            // 更新記錄的狀態
            _lastCanvasWidth = canvasWidth;
            _lastCanvasHeight = canvasHeight;
            _lastMinY = minY;
            _lastMaxY = maxY;
            _pathNeedsUpdate = false;
            _dataChanged = false;
        }
        #endregion

        #region 渲染函數 Render

        /// <summary>
        /// 當程式調用 <執行 InvalidateVisual()>
        ///     ↓
        /// 設定 dirty 標記(請求需要重畫) <執行 Render()>
        ///     ↓
        /// 等待下個渲染週期，實際繪製到螢幕 <註: 下個渲染週期 電腦硬體和作業系統定義 > 比如電腦 60HZ 更新就是60HZ 
        /// </summary>
        /// 另外這個是屬於底層呼叫，但因為API規定所以一定要用 public 才能遮蔽『override』
        /// <param name="context">繪製上下文</param>
        public override void Render(DrawingContext context)
        {
            // 執行父類的UI跟新，因為顏色粗細什麼都要處裡，但父類中的 Render 是空的所以這一行基本沒有用
            base.Render(context);

            // 建立當前數據的安全副本
            List<float> copy_繪製資料_List;
            SKPath 安全快取路徑;
            lock (_dataLock)
            {
                copy_繪製資料_List = new List<float>(繪製資料_List);

                // === 新增：在這裡更新路徑快取 ===
                if (Bounds.Width > 0 && Bounds.Height > 0)
                {
                    更新路徑快取((float)Bounds.Width, (float)Bounds.Height, copy_繪製資料_List);
                }
                // ✅ 在 lock 裡 clone，確保繪圖時快取不會被其他執行緒改動
                安全快取路徑 = _cachedPath?.Clone();  // 加這行
            }

            // 確保控件有有效的尺寸才進行繪製
            if (Bounds.Width > 0 && Bounds.Height > 0)
            {
               // var 安全快取路徑 = _cachedPath?.Clone(); // 複製一份路徑避免 race condition
                // 您會發現每次跟新都是重新用『圖形產生』繪一個新的圖
                var pr_波形圖 = new 圖形產生(
                    new Rect(Bounds.Size), // 一外框大小決定此圖大小
                    copy_繪製資料_List,
                    SKP_線條屬性,
                    SKP_背景屬性,
                    SKP_Y軸刻度,
                    SKP_XY軸的刻度文字,
                    圖表標題,
                    Rd_繪圖底層ID隔絕.Next(),
                    安全快取路徑 // === 新增：傳入快取的路徑 ===
                );
                // 然後顯示在上面
                context.Custom(pr_波形圖);
                // 確實不是太高效的寫法
            }
        }

        #endregion


        #region 繪圖『圖形產生』物件

        /// <summary>
        /// 執行 Render()
        ///     ↓
        /// 以『圖形產生』建構新的一張圖
        ///     ↓
        /// 繪圖容器.Custom(pr_波形圖) 顯示在圖上面
        /// </summary>
        /// 繼承 Avalonia.Rendering.SceneGraph.ICustomDrawOperation
        ///  Avalonia 自定義繪圖機制的一部分，主要用於 在 UI 控制項上以 SkiaSharp 進行底層繪圖。
        private class 圖形產生 : ICustomDrawOperation
        {
            #region ICustomDrawOperation 參數初始化
            // 繪製邊界
            private readonly Rect DO_圖形大小和位置;
            // 繪製的 List 點
            private readonly List<float> DO_繪製資料_List;

            // 對其上面 畫布基本設定
            private readonly SKPaint DO_SKP_線條屬性;
            private readonly SKPaint DO_SKP_背景屬性;
            private readonly SKPaint DO_SKP_Y軸刻度;
            private readonly SKPaint DO_SKP_XY軸的刻度文字;
            /// 圖表標題
            private readonly string DO_圖表標題;
            /// 實例識別ID
            private readonly int DO_繪圖_ID;
            /// 左邊的間距 
            private readonly float DO_左間距;
            /// === 新增：快取的繪製路徑 ===
            private readonly SKPath DO_快取路徑;

            // 就複製下來的 每次的『Render』都 new 一張新的圖，想要詳細註解看上面的 Render
            public 圖形產生(Rect bounds, List<float> data,
                                       SKPaint linePaint, SKPaint backgroundPaint,
                                       SKPaint axisPaint, SKPaint textPaint,
                                       string title, int instanceId, SKPath cachedPath)
            {
                DO_圖形大小和位置 = bounds;
                DO_繪製資料_List = data;
                DO_SKP_線條屬性 = linePaint;
                DO_SKP_背景屬性 = backgroundPaint;
                DO_SKP_Y軸刻度 = axisPaint;
                DO_SKP_XY軸的刻度文字 = textPaint;
                DO_圖表標題 = title;
                DO_繪圖_ID = instanceId;
                DO_左間距 = 46f;
                DO_快取路徑 = cachedPath; // === 新增：儲存快取路徑的參考 ===
            }

            /// <summary>
            /// Avalonia.Rendering.SceneGraph.ICustomDrawOperation 
            /// 介面規定必須提供『Bounds』這個屬性
            /// </summary>
            public Rect Bounds => DO_圖形大小和位置;

            #endregion

            #region 繪圖函數

            /// <summary>
            /// 獲取 Skia 畫布並執行繪製
            /// 進行底層，繪圖容器的租借，從『Avalonia』租用到的『Skia_畫布』
            /// 以『繪圖』函數在進行繪畫
            /// </summary>
            /// <param name="繪圖容器"> 取自 Avalonia.Media.ImmediateDrawingContext</param>
            public void Render(ImmediateDrawingContext 繪圖容器)
            {
                try
                {
                    // 嘗試獲取 SkiaSharp API 功能
                    // 引用 Avalonia.Skia.ISkiaSharpApiLeaseFeature 讀取
                    var 容器 = 繪圖容器.TryGetFeature<ISkiaSharpApiLeaseFeature>();
                    if (容器 == null) return; // 若無法取的則返回

                    // 租用 Skia 的畫圖資源（ISkiaSharpApiLease）
                    using var 租用 = 容器.Lease();
                    var Skia_畫布 = 租用.SkCanvas;
                    if (Skia_畫布 == null) return; // 都以『null』判斷有無租借成功

                    // 執行實際的圖表繪製
                    繪圖(Skia_畫布);
                }
                catch (Exception) { }
            }

            /// <summary>
            /// 『Render』產生一可以繪圖的畫布物件
            /// 此函數進行繪圖
            /// </summary>
            /// <param name="Skia_畫布"></param>
            private void 繪圖(SKCanvas Skia_畫布)
            {
                float 畫布_寬 = (float)DO_圖形大小和位置.Width;
                float 畫布_高 = (float)DO_圖形大小和位置.Height;
                if (畫布_寬 <= 0 || 畫布_高 <= 0) return;

                // 設定成改變(自適應，切割等等)圖
                Skia_畫布.Save();
                try
                {
                    // 背景填充覆蓋整個畫布的矩形（背景）
                    Skia_畫布.DrawRect(0, 0, 畫布_寬, 畫布_高, DO_SKP_背景屬性);
                    // 只允許在這個矩形區域內繪圖
                    Skia_畫布.ClipRect(new SKRect(0, 0, 畫布_寬, 畫布_高));

                    // Skia_畫布.DrawText(DO_圖表標題, 10, 20, DO_SKP_XY軸的刻度文字);

                    if (DO_繪製資料_List.Count == 0) return;

                    float maxY = DO_繪製資料_List.Max();
                    float minY = DO_繪製資料_List.Min();
                    // if (maxY <= minY) maxY = maxY  ;

                    // 輸入畫布和高，minY 和 maxY 判斷
                    Y軸的自適應(Skia_畫布, 畫布_高, minY, maxY);

                    // === 修改：直接使用快取的路徑，不再重新計算 ===
                    if (DO_快取路徑 != null &&
                        DO_快取路徑.Handle != IntPtr.Zero &&
                        !DO_快取路徑.IsEmpty &&
                        DO_SKP_線條屬性 != null)
                    {
                        try
                        {

                            using var 安全路徑 = new SKPath(DO_快取路徑);

                            Skia_畫布.DrawPath(安全路徑, DO_SKP_線條屬性);
                        }
                        catch (Exception ex)
                        {
                            Console.WriteLine("Skia 畫圖失敗: " + ex.Message);
                        }
                    }
                }
                finally
                {
                    Skia_畫布.Restore();
                }
            }

            /// <summary>
            /// 看下面註解
            /// </summary>
            /// <param name="Skia_畫布"></param>
            /// <param name="高"></param>
            /// <param name="minY"></param>
            /// <param name="maxY"></param>
            private void Y軸的自適應(SKCanvas Skia_畫布, float 高, float minY, float maxY)
            {
                int 要刻度數 = 7;    // ➤ 想要切出幾個刻度（Y 軸被分成幾段）
                float 左間距 = DO_左間距;  // ➤ 距離左邊邊界多少像素開始畫 Y 軸（保留空間畫文字）

                for (int i = 0; i <= 要刻度數; i++)
                {
                    // ➤ 計算目前這個刻度的 y 位置（從底部往上畫）
                    float y = 高 - (i * 高 / 要刻度數);

                    // ➤ 根據比例換算出這個 y 所對應的實際資料值
                    float value = minY + (i * (maxY - minY ) / 要刻度數);

                    // ➤ 畫短線（刻度線），線的長度為 10px（從 左間距-5 到 左間距+5）
                    Skia_畫布.DrawLine(左間距 - 5, y, 左間距 + 5, y, DO_SKP_Y軸刻度);


                    // ✅ 跳過最上與最下兩個刻度文字與刻度線
                    if (i == 0 || i == 要刻度數)
                        continue;

                    // ➤ 把這個資料值顯示成文字（小數點後 3 位），畫在左邊
                    var text = value.ToString("F3");
                    Skia_畫布.DrawText(text, 5, y + 4, DO_SKP_XY軸的刻度文字);  // x=5 是靠左留空
                }
                // ➤ 最後畫一條主 Y 軸線（垂直線），從上到下，位置為 『左間距』
                Skia_畫布.DrawLine(左間距, 0, 左間距, 高, DO_SKP_Y軸刻度);
            }

            // === 移除原本的 DrawDataLine 方法，因為已經用快取路徑取代 ===

            #endregion

            #region 其他事件

            /// <summary>
            /// 點擊測試 - 此圖表不響應滑鼠點擊
            /// </summary>
            public bool HitTest(Point point) => false;

            /// <summary>
            /// 相等性比較 - 基於實例ID判斷是否為同一個繪製操作
            /// </summary>
            public bool Equals(ICustomDrawOperation? other) => other is 圖形產生 op && op.DO_繪圖_ID == DO_繪圖_ID;

            /// <summary>
            /// 資源釋放 - 實現IDisposable介面（目前無需特殊處理）
            /// </summary>
            public void Dispose() { }
            
            #endregion
        }

        #endregion
    }

    #region 單通道的繼承程式



    /// <summary>
    /// 通道1圖表 - 紅色線條的具體實現
    /// 繼承基礎圖表類並指定紅色作為線條顏色
    /// </summary>
    public class Skia_通道_1 : SkiaChart_Base
    {
        /// <summary>線條顏色：紅色 (RGB: 220, 20, 20)</summary>
        // CH1：柔和天藍色 (#8BB4D8)
        protected override SKColor 線條顏色 => new SKColor(65, 95, 125);
        //protected override string 圖表標題 => "ch1";  // 可選的圖表標題
    }

    /// <summary>
    /// 通道2圖表 - 藍色線條的具體實現
    /// 繼承基礎圖表類並指定藍色作為線條顏色
    /// </summary>
    public class Skia_通道_2 : SkiaChart_Base
    {
        // CH2：柔和薄荷綠 (#A8D8B0)  
        protected override SKColor 線條顏色 => new SKColor(85, 125, 85);
        //protected override string 圖表標題 => "ch2";  // 可選的圖表標題
    }

    /// <summary>
    /// 通道3圖表 - 綠色線條的具體實現
    /// 繼承基礎圖表類並指定綠色作為線條顏色
    /// </summary>
    public class Skia_通道_3 : SkiaChart_Base
    {
        // CH3：柔和奶黃色 (#F4D58D)
        protected override SKColor 線條顏色 => new SKColor(140, 125, 75);
        //protected override string 圖表標題 => "ch3";  // 可選的圖表標題
    }

    /// <summary>
    /// 通道4圖表 - 紫色線條的具體實現
    /// 繼承基礎圖表類並指定紫色作為線條顏色
    /// </summary>
    public class Skia_通道_4 : SkiaChart_Base
    {
        // CH4：柔和粉紫色 (#E8B4CB)
        protected override SKColor 線條顏色 => new SKColor(130, 85, 115);
        //protected override string 圖表標題 => "ch4";  // 可選的圖表標題
    }


    /// <summary>
    /// 通道1圖表 - 紅色線條的具體實現
    /// 繼承基礎圖表類並指定紅色作為線條顏色
    /// </summary>
    public class DAQ_ch_1 : SkiaChart_Base
    {
        /// <summary>線條顏色：紅色 (RGB: 220, 20, 20)</summary>
        // CH1：柔和天藍色 (#8BB4D8)
        protected override SKColor 線條顏色 => new SKColor(65, 95, 125);
        //protected override string 圖表標題 => "ch1";  // 可選的圖表標題
    }

    /// <summary>
    /// 通道2圖表 - 藍色線條的具體實現
    /// 繼承基礎圖表類並指定藍色作為線條顏色
    /// </summary>
    public class DAQ_ch_2 : SkiaChart_Base
    {
        // CH2：柔和薄荷綠 (#A8D8B0)  
        protected override SKColor 線條顏色 => new SKColor(85, 125, 85);
        //protected override string 圖表標題 => "ch2";  // 可選的圖表標題
    }

    /// <summary>
    /// 通道3圖表 - 綠色線條的具體實現
    /// 繼承基礎圖表類並指定綠色作為線條顏色
    /// </summary>
    public class DAQ_ch_3 : SkiaChart_Base
    {
        // CH3：柔和奶黃色 (#F4D58D)
        protected override SKColor 線條顏色 => new SKColor(140, 125, 75);
        //protected override string 圖表標題 => "ch3";  // 可選的圖表標題
    }

    /// <summary>
    /// 通道4圖表 - 紫色線條的具體實現
    /// 繼承基礎圖表類並指定紫色作為線條顏色
    /// </summary>
    public class DAQ_ch_4 : SkiaChart_Base
    {
        // CH4：柔和粉紫色 (#E8B4CB)
        protected override SKColor 線條顏色 => new SKColor(130, 85, 115);
        //protected override string 圖表標題 => "ch4";  // 可選的圖表標題
    }

    #endregion
}