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
    /// XY座標點結構 - 輕量級的座標點表示
    /// </summary>
    public readonly struct XYPoint
    {
        public readonly float X;
        public readonly float Y;

        public XYPoint(float x, float y)
        {
            X = x;
            Y = y;
        }
    }

    /// <summary>
    /// SkiaXY花瓣圖基礎抽象類 - 提供XY散點圖繪製的基本功能
    /// 專為高頻資料設計，支援長時間運行的效能優化
    /// </summary>
    public abstract class SkiaXYChart_Base : Control
    {
        #region 各項參數的初始化

        /// 數據鎖 - 用於保護多執行緒環境下的數據存取安全
        private readonly object _dataLock = new object();
        /// XY座標點列表 - 存儲要繪製的座標點
        private readonly List<XYPoint> 繪製座標點_List = new List<XYPoint>();
        /// 渲染實例ID生成器
        private readonly Random Rd_繪圖底層ID隔絕 = new Random();

        // === 快取相關 ===
        /// 快取的繪製點陣列，避免每次重新轉換
        private SKPoint[] _cachedPoints = new SKPoint[0];
        /// 標記點陣列是否需要更新
        private bool _pointsNeedsUpdate = true;
        /// 記錄上次計算時的畫布尺寸
        private float _lastCanvasWidth = 0;
        private float _lastCanvasHeight = 0;
        /// 記錄上次的資料範圍
        private float _lastMinX = 0, _lastMaxX = 0, _lastMinY = 0, _lastMaxY = 0;
        /// 資料變化的標記
        private bool _dataChanged = true;

        // 繪圖屬性
        private readonly SKPaint SKP_點屬性;
        private readonly SKPaint SKP_背景屬性;
        private readonly SKPaint SKP_軸線屬性;
        private readonly SKPaint SKP_刻度文字;

        // 資料管理參數 - 針對高頻資料優化
        private int 最大資料點數 = 2000;  // 增加到8000點，適合高頻顯示
        protected abstract SKColor 點顏色 { get; }
        protected virtual float 點大小 => 2.5f;  // 稍小的點適合密集資料
        protected virtual string 圖表標題 => "";

        protected SkiaXYChart_Base()
        {
            SKP_點屬性 = new SKPaint
            {
                Color = 點顏色,
                IsAntialias = true,
                Style = SKPaintStyle.Fill  // 填充圓點
            };

            SKP_背景屬性 = new SKPaint
            {
                Color = SKColors.Black,
                Style = SKPaintStyle.Fill,
                IsAntialias = false
            };

            SKP_軸線屬性 = new SKPaint
            {
                Color = SKColors.Gray,
                IsAntialias = true,
                StrokeWidth = 1.5f,
                Style = SKPaintStyle.Stroke
            };

            SKP_刻度文字 = new SKPaint
            {
                Color = SKColors.White,
                IsAntialias = true,
                TextSize = 11,  // 稍小的字體適合密集軸線
                Style = SKPaintStyle.Fill
            };
        }

        /// <summary>
        /// 物件銷毀時釋放資源
        /// </summary>
        protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e)
        {
            base.OnDetachedFromVisualTree(e);
            // 清理快取陣列
            _cachedPoints = null;
        }

        #endregion

        #region 數據操作

        /// <summary>
        /// 添加單一座標點到花瓣圖中
        /// </summary>
        /// <param name="x">X座標值</param>
        /// <param name="y">Y座標值</param>
        public void 添加座標點(float x, float y)
        {
            lock (_dataLock)
            {
                繪製座標點_List.Add(new XYPoint(x, y));

                // 限制資料點數量，移除最舊的點
                if (繪製座標點_List.Count > 最大資料點數)
                {
                    int 超出數 = 繪製座標點_List.Count - 最大資料點數;
                    繪製座標點_List.RemoveRange(0, 超出數);
                }

                _dataChanged = true;
                _pointsNeedsUpdate = true;
            }
        }

        /// <summary>
        /// 批量添加多筆座標點 - 高效能版本
        /// 適合高頻資料輸入，一次處理多個點
        /// </summary>
        /// <param name="xValues">X座標值列表</param>
        /// <param name="yValues">Y座標值列表</param>
        public void 添加多筆座標點(List<float> xValues, List<float> yValues)
        {
            if (xValues == null || yValues == null || xValues.Count == 0 || yValues.Count == 0)
                return;

            // 取較小的長度，確保配對
            int count = Math.Min(xValues.Count, yValues.Count);

            lock (_dataLock)
            {
                // 預先計算容量，避免多次重新分配
                int newTotal = 繪製座標點_List.Count + count;
                if (newTotal > 最大資料點數)
                {
                    // 計算需要移除的舊資料數量
                    int 需移除數 = newTotal - 最大資料點數;
                    if (需移除數 > 0 && 需移除數 < 繪製座標點_List.Count)
                    {
                        繪製座標點_List.RemoveRange(0, 需移除數);
                    }
                    else if (需移除數 >= 繪製座標點_List.Count)
                    {
                        // 新資料太多，清空舊資料
                        繪製座標點_List.Clear();
                        // 只保留最新的資料
                        int startIndex = Math.Max(0, count - 最大資料點數);
                        count = count - startIndex;
                        for (int i = startIndex; i < xValues.Count && i < yValues.Count && (i - startIndex) < count; i++)
                        {
                            繪製座標點_List.Add(new XYPoint(xValues[i], yValues[i]));
                        }
                        _dataChanged = true;
                        _pointsNeedsUpdate = true;
                        return;
                    }
                }

                // 批量添加新資料
                for (int i = 0; i < count; i++)
                {
                    繪製座標點_List.Add(new XYPoint(xValues[i], yValues[i]));
                }

                _dataChanged = true;
                _pointsNeedsUpdate = true;
            }
        }

        /// <summary>
        /// 重繪畫布 - 使用低優先級避免UI阻塞
        /// </summary>
        public void 重畫畫布()
        {
            Avalonia.Threading.Dispatcher.UIThread.Post(() =>
            {
                InvalidateVisual();
            }, Avalonia.Threading.DispatcherPriority.Background);
        }

        /// <summary>
        /// 清空所有座標點
        /// </summary>
        public void 清空數據()
        {
            lock (_dataLock)
            {
                繪製座標點_List.Clear();
                _cachedPoints = new SKPoint[0];
                _dataChanged = true;
                _pointsNeedsUpdate = true;
            }
            InvalidateVisual();
        }

        /// <summary>
        /// 更新點陣列快取 - 效能關鍵方法
        /// 只有在資料或畫布改變時才重新計算
        /// </summary>
        private void 更新點陣列快取(float canvasWidth, float canvasHeight, List<XYPoint> pointList)
        {
            bool 尺寸已改變 = Math.Abs(_lastCanvasWidth - canvasWidth) > 0.1f ||
                           Math.Abs(_lastCanvasHeight - canvasHeight) > 0.1f;

            if (!_pointsNeedsUpdate && !尺寸已改變 && !_dataChanged)
                return;

            if (pointList.Count == 0)
            {
                _cachedPoints = new SKPoint[0];
                return;
            }

            // 計算資料範圍
            float minX = pointList.Min(p => p.X);
            float maxX = pointList.Max(p => p.X);
            float minY = pointList.Min(p => p.Y);
            float maxY = pointList.Max(p => p.Y);

            // 避免除零錯誤
            if (maxX <= minX) { maxX = minX + 1f; }
            if (maxY <= minY) { maxY = minY + 1f; }

            // 檢查範圍是否改變
            bool 範圍已改變 = Math.Abs(_lastMinX - minX) > 0.001f ||
                           Math.Abs(_lastMaxX - maxX) > 0.001f ||
                           Math.Abs(_lastMinY - minY) > 0.001f ||
                           Math.Abs(_lastMaxY - maxY) > 0.001f;

            if (!_pointsNeedsUpdate && !尺寸已改變 && !_dataChanged && !範圍已改變)
                return;

            // 重新計算點位置
            float 左間距 = 50f;
            float 底間距 = 30f;
            float 圖表寬 = canvasWidth - 左間距 - 10f;
            float 圖表高 = canvasHeight - 底間距 - 10f;

            _cachedPoints = new SKPoint[pointList.Count];

            for (int i = 0; i < pointList.Count; i++)
            {
                var point = pointList[i];

                // 正規化到 0-1 範圍
                float normalizedX = (point.X - minX) / (maxX - minX);
                float normalizedY = (point.Y - minY) / (maxY - minY);

                // 轉換到畫布座標（Y軸翻轉）
                float canvasX = 左間距 + (normalizedX * 圖表寬);
                float canvasY = canvasHeight - 底間距 - (normalizedY * 圖表高);

                _cachedPoints[i] = new SKPoint(canvasX, canvasY);
            }

            // 更新快取狀態
            _lastCanvasWidth = canvasWidth;
            _lastCanvasHeight = canvasHeight;
            _lastMinX = minX; _lastMaxX = maxX;
            _lastMinY = minY; _lastMaxY = maxY;
            _pointsNeedsUpdate = false;
            _dataChanged = false;
        }

        #endregion

        #region 渲染函數

        public override void Render(DrawingContext context)
        {
            base.Render(context);

            // 建立資料的安全副本
            List<XYPoint> copy_繪製座標點_List;
            SKPoint[] 安全快取點陣列;

            lock (_dataLock)
            {
                copy_繪製座標點_List = new List<XYPoint>(繪製座標點_List);

                // 更新點陣列快取
                if (Bounds.Width > 0 && Bounds.Height > 0)
                {
                    更新點陣列快取((float)Bounds.Width, (float)Bounds.Height, copy_繪製座標點_List);
                }

                // 複製快取陣列
                安全快取點陣列 = new SKPoint[_cachedPoints.Length];
                Array.Copy(_cachedPoints, 安全快取點陣列, _cachedPoints.Length);
            }

            if (Bounds.Width > 0 && Bounds.Height > 0)
            {
                var pr_花瓣圖 = new XY圖形產生(
                    new Rect(Bounds.Size),
                    copy_繪製座標點_List,
                    SKP_點屬性,
                    SKP_背景屬性,
                    SKP_軸線屬性,
                    SKP_刻度文字,
                    圖表標題,
                    點大小,
                    Rd_繪圖底層ID隔絕.Next(),
                    安全快取點陣列
                );
                context.Custom(pr_花瓣圖);
            }
        }

        #endregion

        #region XY圖形產生類

        private class XY圖形產生 : ICustomDrawOperation
        {
            private readonly Rect DO_圖形大小和位置;
            private readonly List<XYPoint> DO_繪製座標點_List;
            private readonly SKPaint DO_SKP_點屬性;
            private readonly SKPaint DO_SKP_背景屬性;
            private readonly SKPaint DO_SKP_軸線屬性;
            private readonly SKPaint DO_SKP_刻度文字;
            private readonly string DO_圖表標題;
            private readonly float DO_點大小;
            private readonly int DO_繪圖_ID;
            private readonly SKPoint[] DO_快取點陣列;

            public XY圖形產生(Rect bounds, List<XYPoint> points,
                             SKPaint pointPaint, SKPaint backgroundPaint,
                             SKPaint axisPaint, SKPaint textPaint,
                             string title, float pointSize, int instanceId,
                             SKPoint[] cachedPoints)
            {
                DO_圖形大小和位置 = bounds;
                DO_繪製座標點_List = points;
                DO_SKP_點屬性 = pointPaint;
                DO_SKP_背景屬性 = backgroundPaint;
                DO_SKP_軸線屬性 = axisPaint;
                DO_SKP_刻度文字 = textPaint;
                DO_圖表標題 = title;
                DO_點大小 = pointSize;
                DO_繪圖_ID = instanceId;
                DO_快取點陣列 = cachedPoints;
            }

            public Rect Bounds => DO_圖形大小和位置;

            public void Render(ImmediateDrawingContext 繪圖容器)
            {
                try
                {
                    var 容器 = 繪圖容器.TryGetFeature<ISkiaSharpApiLeaseFeature>();
                    if (容器 == null) return;

                    using var 租用 = 容器.Lease();
                    var Skia_畫布 = 租用.SkCanvas;
                    if (Skia_畫布 == null) return;

                    繪圖(Skia_畫布);
                }
                catch (Exception) { }
            }

            private void 繪圖(SKCanvas Skia_畫布)
            {
                float 畫布_寬 = (float)DO_圖形大小和位置.Width;
                float 畫布_高 = (float)DO_圖形大小和位置.Height;
                if (畫布_寬 <= 0 || 畫布_高 <= 0) return;

                Skia_畫布.Save();
                try
                {
                    // 背景
                    Skia_畫布.DrawRect(0, 0, 畫布_寬, 畫布_高, DO_SKP_背景屬性);
                    Skia_畫布.ClipRect(new SKRect(0, 0, 畫布_寬, 畫布_高));

                    if (DO_繪製座標點_List.Count == 0) return;

                    // 計算座標範圍並繪製軸線
                    繪製XY軸線和刻度(Skia_畫布, 畫布_寬, 畫布_高);

                    // 繪製散點 - 使用快取的點陣列
                    if (DO_快取點陣列 != null && DO_快取點陣列.Length > 0)
                    {
                        for (int i = 0; i < DO_快取點陣列.Length; i++)
                        {
                            var point = DO_快取點陣列[i];
                            Skia_畫布.DrawCircle(point.X, point.Y, DO_點大小, DO_SKP_點屬性);
                        }
                    }
                }
                finally
                {
                    Skia_畫布.Restore();
                }
            }

            private void 繪製XY軸線和刻度(SKCanvas Skia_畫布, float 畫布_寬, float 畫布_高)
            {
                float 左間距 = 50f;
                float 底間距 = 30f;
                float 圖表寬 = 畫布_寬 - 左間距 - 10f;
                float 圖表高 = 畫布_高 - 底間距 - 10f;

                // 計算資料範圍
                float minX = DO_繪製座標點_List.Min(p => p.X);
                float maxX = DO_繪製座標點_List.Max(p => p.X);
                float minY = DO_繪製座標點_List.Min(p => p.Y);
                float maxY = DO_繪製座標點_List.Max(p => p.Y);

                if (maxX <= minX) maxX = minX + 1f;
                if (maxY <= minY) maxY = minY + 1f;

                // 繪製主軸線
                // Y軸（垂直線）
                Skia_畫布.DrawLine(左間距, 10, 左間距, 畫布_高 - 底間距, DO_SKP_軸線屬性);
                // X軸（水平線）
                Skia_畫布.DrawLine(左間距, 畫布_高 - 底間距, 畫布_寬 - 10, 畫布_高 - 底間距, DO_SKP_軸線屬性);

                // Y軸刻度
                int Y軸刻度數 = 5;
                for (int i = 0; i <= Y軸刻度數; i++)
                {
                    float y = 畫布_高 - 底間距 - (i * 圖表高 / Y軸刻度數);
                    float value = minY + (i * (maxY - minY) / Y軸刻度數);

                    Skia_畫布.DrawLine(左間距 - 5, y, 左間距 + 5, y, DO_SKP_軸線屬性);
                    var text = value.ToString("F2");
                    Skia_畫布.DrawText(text, 5, y + 4, DO_SKP_刻度文字);
                }

                // X軸刻度
                int X軸刻度數 = 5;
                for (int i = 0; i <= X軸刻度數; i++)
                {
                    float x = 左間距 + (i * 圖表寬 / X軸刻度數);
                    float value = minX + (i * (maxX - minX) / X軸刻度數);

                    Skia_畫布.DrawLine(x, 畫布_高 - 底間距 - 5, x, 畫布_高 - 底間距 + 5, DO_SKP_軸線屬性);
                    var text = value.ToString("F2");
                    Skia_畫布.DrawText(text, x - 15, 畫布_高 - 10, DO_SKP_刻度文字);
                }
            }

            public bool HitTest(Point point) => false;
            public bool Equals(ICustomDrawOperation? other) => other is XY圖形產生 op && op.DO_繪圖_ID == DO_繪圖_ID;
            public void Dispose() { }
        }

        #endregion
    }

    #region 具體實現類

    /// <summary>
    /// 花瓣圖1 - 紅色點
    /// </summary>
    public class Skia_花瓣圖_1 : SkiaXYChart_Base
    {
        protected override SKColor 點顏色 => new SKColor(220, 20, 20, 180); // 半透明紅色
    }

    /// <summary>
    /// 花瓣圖2 - 藍色點
    /// </summary>
    public class Skia_花瓣圖_2 : SkiaXYChart_Base
    {
        protected override SKColor 點顏色 => new SKColor(20, 100, 220, 180); // 半透明藍色
    }

    #endregion
}