using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Interactivity;
using Avalonia.Markup.Xaml;
using Avalonia.Threading;
using System.Threading;

namespace Clairvoyance;

/// <summary>
/// 真正給使用者提供的 MyMessageBox
/// </summary>
public sealed class MyMessageBox : _MyMessageBoxShow_ { 

    // 鎖死建構式，不外借
    private MyMessageBox() { }  

    /// <summary>
    /// 顯示文字等等
    /// </summary>
    public static void Show()
    {

        // ✅ 讓 MessageBox 顯示程式碼在 UI 執行緒中執行，異步排程方法（非同步排入主執行緒）
        Dispatcher.UIThread.Post(() =>
        {
            _MyMessageBoxShow_ msgBox = new MyMessageBox();
            msgBox.Show(); // 可改用 ShowDialog() 依需求
        });
    }

}

/// <summary>
/// 父項，的 MessageBoxShow 給子項
/// </summary>
/// 看到這個註解的你，一定很好奇，為何需要用成抽象類別，因為為避免使用者，
/// 使用 _MyMessageBoxShow_ 建構程式，所以用抽象類別把，建構封鎖，
/// 只要使用者不要亂繼承元件就不會被錯誤讀取，在看不懂註解，看上面的 MyMessageBox 怎麼使用這個物件的
public abstract partial class _MyMessageBoxShow_ : Window
{
    protected _MyMessageBoxShow_()
    {
        InitializeComponent();
    }
    private void Bu_null_Minimize_Click(object? sender, RoutedEventArgs e)
    {
        this.WindowState = WindowState.Minimized;
    }

    private void Bu_null_MaximizeOrRestore_Click(object? sender, RoutedEventArgs e)
    {
        if (this.WindowState == WindowState.Maximized)
            this.WindowState = WindowState.Normal;
        else
            this.WindowState = WindowState.Maximized;
    }

    private void Bu_null_Close_Click(object? sender, RoutedEventArgs e)
    {
        this.Close(); // 關閉視窗
    }
}